"""Identification des objets : hybride cloud/local via Ollama.

Pipeline vision :
    1-3 photos + contexte vendeur -> /api/chat Ollama -> JSON contraint -> dict.

Deux moteurs possibles (mode hybride, activé par VISION_CLOUD=1) :
    - CLOUD d'abord : modèles "<tag>-cloud" tournés sur les GPU d'Ollama.com
      (rapide, ~2-5 s/scan) ; à la moindre indisponibilité (pas signé, pas de
      réseau, quota...) on passe au suivant puis au LOCAL sans bloquer ;
      un échec cloud est mémorisé 10 min (_DELAI_CACHE_PANNE) pour ne pas
      alourdir chaque scan de la latence de l'échec.
    - LOCAL : le petit modèle téléchargé (défaut gemma4:e2b), 100 % offline.

Dans tous les cas le modèle ne produit que la VISION (JSON court) ; le
reste — catégorie, fourchette, rareté, textes d'annonce — est calculé
par app/estimateur.py, zéro jeton.
"""
import base64
import json
import os
import re
import time

import requests

OLLAMA_URL = "http://localhost:11434"
# Overridable par variable d'environnement (ex: VISION_MODELE=gemma4:e4b ./run.sh)
MODELE = os.environ.get("VISION_MODELE", "gemma4:e2b")
# Le chargement du modèle sur CPU dure 2-3 min : on le garde en mémoire.
KEEP_ALIVE = "4h"

# --- mode hybride (optionnel, VISION_CLOUD=1) -----------------------------
ACTIVER_CLOUD = os.environ.get("VISION_CLOUD", "0").lower() in ("1", "true", "oui", "yes")
MODELES_CLOUD = [
    m.strip()
    for m in os.environ.get("VISION_MODELES_CLOUD", "glm-5.3-flash:cloud").split(",")
    if m.strip()
]
_DELAI_CACHE_PANNE = 600        # après un échec cloud, 10 min en local
_date_echec_cloud = 0.0

# Le modèle ne produit que ce que SEUL un modèle de vision peut donner
# (lecture de la photo). Le reste — catégorie, rareté, fourchette, texte
# d'annonce — est calculé par app/estimateur.py, sans jeton : sur CPU
# (~5 tokens/s), chaque champ de sortie économisé = secondes gagnées.
CONSIGNE = """

Tu vois 1 à 3 photos du MÊME objet d'occasion (angles différents : face, dos, détails). Tu es un expert en brocante et tu ne te fies QU'À l'image.

L'OBJET À DÉCRIRE est le SUJET des photos : celui qui est net, centré, photographié par le vendeur. Les objets d'arrière-plan (bureau, ordinateur, murs, bibelots) ne comptent PAS, même s'ils sont gros — sauf si une photo les montre net et seul.

Étape 1 — LECTURE : transcris à la lettre chaque texte, gravure, étiquette, logo et chiffre visibles, PHOTO PAR PHOTO (photo1:, photo2:... Fusionne : un détail lisible sur une seule photo vaut pour l'objet entier.
Étape 2 — OBJET : nom courant le plus précis possible, avec variante/édition/couleur VISIBLES. Si les photos montrent une boîte ou un emballage d'origine, identifie le PRODUIT qu'il contient (ex : "Apple Pencil 1re génération") et précise "boîte d'origine".
Étape 3 — MARQUE/MODÈLE seulement si lisibles sur l'objet ou l'emballage, sinon chaîne vide. N'ÉCRIS JAMAIS le mot vide.
Étape 4 — ÉTAT d'après les détails visibles (rayures, usure, poussière, câble...) : une de: neuf,excellent,bon,correct,use,hs.
Étape 5 — FOURCHETTE : prix d'occasion réaliste en euros (connaissance du marché de la seconde main + état visible) ; 0 si tu n'en sais vraiment rien.
Étape 6 — MOTS_CLES : 2-4 mots pour retrouver cet objet en ligne.
Réponds uniquement avec ce JSON, sur une seule ligne, sans texte autour :
{"texte_visible":"photo1: ... | photo2: ... (vide si aucun)","objet":"nom courant précis","marque":"nom si clairement lisible/emblématique, sinon \\"\\"","modele":"référence si lisible, sinon \\"\\"","etat":"une de: neuf,excellent,bon,correct,use,hs","prix_min":entier,"prix_max":entier,"mots_cles":"2-4 mots","confiance":1.0 si marque lisible, sinon 0.6-0.8}
"""


def extraire_json(texte: str) -> dict:
    """Récupère le dernier objet JSON équilibré de la réponse.

    "Dernier" et non "premier" : les modèles qui réfléchissent en ligne
    (thinking dans le content) peuvent citer des exemples JSON dans leur
    réflexion ; le JSON demandé vient en dernier, après leur pensée. Tolère
    les fences ```.
    """
    texte = re.sub(r"```(?:json)?", "", texte)
    debut = texte.find("{")
    if debut == -1:
        raise ValueError(f"pas de JSON dans la réponse : {texte[:200]!r}")
    objets = []
    profondeur = 0
    depart = debut
    for i, caractere in enumerate(texte[debut:], start=debut):
        if caractere == "{":
            if profondeur == 0:
                depart = i
            profondeur += 1
        elif caractere == "}":
            profondeur -= 1
            if profondeur == 0:
                objets.append(texte[depart : i + 1])
    if not objets:
        raise ValueError("JSON non terminé dans la réponse du modèle")
    try:
        return json.loads(objets[-1])        # réponse finale, après le thinking
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON illisible : {e}") from e


# Filet anti-vide : une réponse sans AUCUN champ rempli (ça arrive une fois
# de temps en temps, cf. scan de hier 17h) est redemandée UNE fois au même
# moteur. Un mauvais texte aléatoire vaut mieux qu'une page vide.
_REPRISE_VIDE = (
    "IMPORTANT : ta réponse précédente était vide ou incomplète. "
    "Renvoie maintenant le JSON demandé avec TOUS les champs remplis d'après "
    "ce que tu vois vraiment. Seuls marque/modele restent \"\" si illisibles."
)


def _ident_vide(ident: dict) -> bool:
    return not any(
        (ident.get(cle) or "").strip()
        for cle in ("objet", "texte_visible", "marque")
    )


def modele_disponible() -> bool:
    """True si le modèle local est bien téléchargé."""
    try:
        liste = requests.get(OLLAMA_URL + "/api/tags", timeout=5).json()
        return any(
            m.get("name", "").startswith(MODELE) for m in liste.get("models", [])
        )
    except requests.RequestException:
        return False


def message_complet(nom_modele: str, contexte: str = "") -> str:
    """Consigne + balises qui dépendent du moteur + contexte du vendeur."""
    message = CONSIGNE
    # Les modèles Qwen raisonnent par défaut. Sur CPU ce thinking coûte
    # 20-40 min par photo → /no_think en LOCAL. Sur CLOUD (-cloud), le
    # modèle garde le DROIT de réfléchir : les GPU distants font à ~100
    # jetons/s ce que le CPU de Julien fait en une demi-heure.
    if "qwen" in nom_modele.lower() and ":cloud" not in nom_modele:
        message += " /no_think"
    if ":cloud" in nom_modele:
        # en cloud il y a de la marge : le modèle rédige aussi l'annonce
        # (naturelle) ; le local reste en JSON court et le gabarit Python.
        # La clé est insérée DANS le gabarit JSON, sinon elle est ignorée.
        avec_annonce = message.replace(
            '"confiance":1.0 si marque lisible, sinon 0.6-0.8}',
            '"annonce":"Annonce PROFESSIONNELLE en 3 à 5 phrases COURTES et sérieuses : 1) l\'objet et ce qui le rend recherché ; 2) l\'état réel avec les défauts visibles précisés (honnêteté exigée) ; 3) ce qui est inclus (boîte, câble, notice) si visible ; 4) remise en main possible ou envoi soigné. Ton de vendeur fiable : aucun emoji, aucune majuscule criarde, aucun prix, ZÉRO invention ; les infos du contexte vendeur sont signalées comme « précision du vendeur »","confiance":1.0 si marque lisible, sinon 0.6-0.8}',
        )
        message = avec_annonce if avec_annonce != message else (
            message
            + '\n6. Ton JSON doit aussi contenir la clé "annonce" : 3-4 phrases naturelles en français décrivant l\'objet pour une annonce, sans prix et sans invention.'
        )
    indice = (contexte or "").strip()[:300]
    if indice:
        message += (
            "\n\nContexte fourni par le vendeur (un indice à CROISER avec les "
            "photos, qui restent la référence s'il y a contradiction) : "
            f'"{indice}"'
        )
    return message


def _payload_pour(nom_modele: str, images: list, contexte: str = "",
                  pousse: str = "") -> dict:
    message = message_complet(nom_modele, contexte)
    if pousse:
        message += "\n\n" + pousse
    return {
        "model": nom_modele,
        "stream": False,
        # Gemma 4 raisonne par défaut : sans cette ligne, la réponse part
        # dans le champ "thinking" et s'interrompt avant le JSON.
        "think": False,
        # garde le modèle local en RAM (sinon 2-3 min de rechargement par scan)
        "keep_alive": KEEP_ALIVE,
        # JSON court + fourchette : ~150 tokens en direct ; sur cloud, la
        # réflexion est permise : budget génération élargi
        "options": {
            "temperature": 0.2,
            "num_predict": 1500 if ":cloud" in nom_modele else 360,
        },
        "messages": [
            {
                "role": "user",
                "content": message_complet(nom_modele, contexte),
                "images": [base64.b64encode(im).decode() for im in images],
            },
        ],
    }


def _essayer_moteur(nom_modele: str, images: list, contexte: str = "",
                    pousse: str = "") -> dict | None:
    """Fait parler UN moteur.

    Retourne la réponse JSON d'Ollama, ou None si le moteur est
    indisponible (pas signé, pas de réseau, modèle absent, quota...) :
    ce n'est pas une erreur de pipeline, on passe simplement au suivant.
    """
    global _date_echec_cloud
    reponse = requests.post(
        OLLAMA_URL + "/api/chat",
        json=_payload_pour(nom_modele, images, contexte, pousse),
        timeout=150 if ":cloud" in nom_modele else 600,
    )
    if reponse.status_code in (401, 403, 404, 407, 500, 502, 503, 504):
        # indisponible pour ce moteur : repli, non bloquant
        if ":cloud" in nom_modele:
            _date_echec_cloud = time.time()
        return None
    if reponse.status_code == 400:
        raise RuntimeError(
            "Ollama a refusé la photo (HTTP 400) même après normalisation : "
            f"{reponse.text[:200]}"
        )
    reponse.raise_for_status()
    return reponse.json()


def _reponse_vers_ident(reponse: dict) -> dict:
    """JSON Ollama -> dict identification enrichie (categorie/prix/annonce)."""
    message = reponse["message"]
    contenu = message.get("content", "") or ""
    if not contenu.strip():
        # repli : le mode thinking peut parfois renvoyer le tout dedans
        contenu = message.get("thinking", "") or ""
    ident = extraire_json(contenu)
    # le modèle a fini son travail de vision : le reste est calculé ici
    from .estimateur import enrichir

    ident = enrichir(ident)
    # garde-fous : valeurs numériques exploitables
    ident["confiance"] = min(1.0, max(0.0, float(ident.get("confiance") or 0.5)))
    return ident


def identifier(images: list[bytes], contexte: str = "") -> dict:
    """1 à 3 photos -> identification structurée.

    Cloud d'abord si activé (+ moteur rapide), sinon local ; l'échec ne
    remonte que si TOUS les moteurs échouent. Une réponse TOTALEMENT vide
    est redemandée une fois au même moteur (filet anti-vide).
    """
    if isinstance(images, (bytes, bytearray)):     # tolère un appel mono-photo
        images = [images]

    def complete(candidat: dict | None, nom_moteur: str, images, contexte) -> dict:
        """Applique le filet anti-vide à une réponse (une reprise max)."""
        if candidat is None or not _ident_vide(candidat):
            return candidat
        reprise = _essayer_moteur(nom_moteur, images, contexte,
                                  pousse=_REPRISE_VIDE)
        if reprise is None:
            return candidat
        try:
            deuxieme = _reponse_vers_ident(reprise)
        except (json.JSONDecodeError, ValueError, KeyError):
            return candidat
        return deuxieme if not _ident_vide(deuxieme) else candidat

    # 1) moteurs cloud (mode hybride, dans l'ordre de la liste)
    global _date_echec_cloud
    if ACTIVER_CLOUD and time.time() - _date_echec_cloud > _DELAI_CACHE_PANNE:
        for nom_cloud in MODELES_CLOUD:
            try:
                reponse = _essayer_moteur(nom_cloud, images, contexte)
            except requests.RequestException:
                _date_echec_cloud = time.time()
                continue
            if reponse is None:
                continue
            try:
                ident = _reponse_vers_ident(reponse)
            except (json.JSONDecodeError, ValueError, KeyError):
                continue          # réponse cloud inexploitable -> moteur suivant
            ident = complete(ident, nom_cloud, images, contexte) or ident
            ident["moteur"] = "cloud · " + nom_cloud
            return ident

    # 2) moteur local (repli automatique, ou défaut si cloud inactivé)
    if not modele_disponible():
        raise RuntimeError(
            f"le modèle {MODELE} n'est pas téléchargé (ollama pull {MODELE})"
        )
    reponse = _essayer_moteur(MODELE, images, contexte)
    if reponse is None:
        raise RuntimeError("le serveur Ollama local est injoignable")
    ident = _reponse_vers_ident(reponse)
    ident = complete(ident, MODELE, images, contexte) or ident
    ident["moteur"] = "local · " + MODELE
    return ident
