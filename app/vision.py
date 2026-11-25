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
CONSIGNE = """Tu vois une ou plusieurs photos du MÊME objet d'occasion (face, dos, détails). Tu ne rapportes QUE ce qu'elles montrent.
1. Transcris à la lettre chaque texte/gravure visible, sans rien inventer.
2. Si la photo montre une boîte ou un emballage d'origine, identifie le PRODUIT qu'il contient (ex : "Apple Pencil 1re génération") et précise "boîte d'origine" dans l'objet ; ne réponds "boîte" dans objet QUE si tu ne peux pas savoir ce qu'elle contenait.
3. Marque/modèle seulement si lisibles sur l'objet ou l'emballage, sinon chaîne vide.
4. Réponds uniquement avec ce JSON, sur une seule ligne, sans texte autour :
{"texte_visible":"textes lus séparés par ' | ' (vide si aucun)","objet":"nom courant précis","marque":"nom si clairement lisible/emblématique, sinon \"\"","modele":"référence si lisible, sinon \"\"","etat":"une de: neuf,excellent,bon,correct,use,hs","prix_min":entier,"prix_max":entier,"mots_cles":"2-4 mots","confiance":1.0 si marque lisible, sinon 0.6-0.8}
5. prix_min/prix_max : fourchette d'occasion réaliste en euros d'après l'état visible et ta connaissance du marché de la seconde main ; si tu n'en sais vraiment rien, mets 0. Champs marque/modele : s'il n'y a rien de lisible, laisse-les comme chaînes vides "", n'écris jamais le mot vide."""


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
            '"annonce":"3-4 phrases naturelles en français : l\'usage de l\'objet, son état précis, ce qu\'on remarque de près ; rien d\'inventé, pas de prix ; les infos du contexte vendeur sont signalées comme précision","confiance":1.0 si marque lisible, sinon 0.6-0.8}',
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


def _payload_pour(nom_modele: str, images: list, contexte: str = "") -> dict:
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


def _essayer_moteur(nom_modele: str, images: list, contexte: str = "") -> dict | None:
    """Fait parler UN moteur.

    Retourne la réponse JSON d'Ollama, ou None si le moteur est
    indisponible (pas signé, pas de réseau, modèle absent, quota...) :
    ce n'est pas une erreur de pipeline, on passe simplement au suivant.
    """
    global _date_echec_cloud
    reponse = requests.post(
        OLLAMA_URL + "/api/chat",
        json=_payload_pour(nom_modele, images, contexte),
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
    remonte que si TOUS les moteurs échouent.
    """
    if isinstance(images, (bytes, bytearray)):     # tolère un appel mono-photo
        images = [images]

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
    ident["moteur"] = "local · " + MODELE
    return ident
