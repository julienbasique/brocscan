"""Enrichissement "métier" calculé côté code — zéro jeton de LLM.

Pour gagner de la vitesse sur CPU (≈5 tokens/s), le modèle Gemma ne produit
plus que les infos qu'il EST LE SEUL à pouvoir donner (ce qu'il voit sur la
photo : textes, objet, marque, état). Tout le reste — catégorie, rareté,
fourchette de prix, description de annonce — est déduit ici, en Python :

  1. catégorie = mots-clés de l'objet/mots_cles/marque ;
  2. fourchette = table par catégorie, modulée par l'état et la marque ;
  3. rareté = heuristique marque/confiance/catégorie collectionnable.

Ces fourchettes restent des ESTIMATIONS larges : le juge de paix reste les
liens "ventes terminées" eBay fournis par app/market.py.
"""
import unicodedata

# --- catégorisation par mots-clés (ordre = priorité) ----------------------
_MOTS_CLES_CATEGORIE = [
    ("montre_bijou", ["montre", "casio", "seiko", "rolex", "bague", "collier", "bijou", "pendantif", "pendentif"]),
    ("carte_collection", ["pokemon", "pokémon", "yu-gi-oh", "yugioh", "magic", "carte à collectionner", "carte de collection", "carte pokemon"]),
    ("figurine", ["figurine", "funko", "banpresto", "maquette", "statuette personnage"]),
    ("jeu_video", ["jeu video", "jeu vidéo", "cartouche", "playstation", "nintendo", "xbox", "game boy", "gameboy", "consoles"]),
    ("vinyle_cd", ["vinyle", "33 tours", "45 tours", "disque", "cassette", "cd ", "compact disc"]),
    ("electronique", ["telephone", "téléphone", "iphone", "smartphone", "ordinateur", "laptop", "tablette", "ipad", "macbook", "ipod", "apple pencil", "pencil", "stylet", "console", "ps4", "ps5", "xbox", "switch", "casque", "appareil photo", "reflex", "objectif", "enceinte", "airpods", "drone", "camera", "caméra", "numerique", "numérique", "imprimante", "baladeur", "walkman", "radio"]),
    ("electromenager", ["lave-linge", "lave linge", "machine a laver", "machine à laver", "frigo", "refrigerateur", "réfrigérateur", "congelateur", "congélateur", "micro-ondes", "aspirateur", "lave-vaisselle", "seche-linge", "sèche-linge", "four ", "plaque de cuisson"]),
    ("meuble", ["armoire", "commode", "canape", "canapé", "buffet", "étagere", "étagère", "fauteuil", "bureau", "lit ", "chaise", "table basse", "table à manger"]),
    ("deco", ["vase", "tableau", "cadre", "miroir", "lampe", "lustre", "sculpture", "argenterie", "menagere", "ménagère"]),
    ("livre", ["livre", "roman", "bd ", "bande dessinee", "bande dessinée", "manga", "dictionnaire", "atlas", "magazine", "comic"]),
    ("jouet", ["peluche", "doudou", "lego", "playmobil", "barbie", "hot wheels", "jouet", "puzzle", "dans un jeu", "circuit"]),
    ("cuisine", ["casserole", "poêle", "poele", "couvert", "assiette", "porcelaine", "cristal", "faïence", "faience", "limoges", "cafetiere", "cafetière", "tasse", "saladier", "moule ", "thermos"]),
    ("outil", ["perceuse", "visseuse", "meuleuse", "scie", "marteau", "tournevis", "cle ", "clé ", "mètre", "metre", "outillage", "equerre", "équerre", "rabot", "etabli", "établi", "echelle", "échelle"]),
    ("sport_loisir", ["moto", "scooter", "velo", "vélo", "vtt", "ski", "snowboard", "golf", "tennis", "raquette", "trottinette", "peche", "pêche", "camping", "tente", "roller", "skate", "kayak", "surf"]),
    ("vetement", ["chemise", "tshirt", "t-shirt", "pull", "pantalon", "jean", "robe", "veste", "blouson", "manteau", "sweat", "polo", "jupe", "costume", "chaquète", "chaquette", "gilet", "echarpe", "écharpe", "casquette"]),
    ("chaussures", ["basket", "sneaker", "chaussure", "botte", "sandale", "derby", "escarpin", "méribel", "meribel"]),
    ("sac", ["sac ", "sacoche", "pochette", "porte-monnaie", "portefeuille", "cartable", "bagage", "valise"]),
]

_CATEGORIES_CONNUES = {
    "vetement", "chaussures", "sac", "montre_bijou", "electronique",
    "electromenager", "meuble", "deco", "livre", "jeu_video", "vinyle_cd",
    "carte_collection", "figurine", "jouet", "outil", "cuisine",
    "sport_loisir", "autre",
}

# --- fourchettes de base (état "bon", France, occasion) ------------------
# (min, max) en euros volontairement LARGE : la précision vient des
# ventes terminées eBay (liens fournis), pas de cette table.
_FOURCHETTES = {
    "vetement": (4, 25), "chaussures": (10, 40), "sac": (10, 60),
    "montre_bijou": (15, 120), "electronique": (15, 150),
    "electromenager": (20, 120), "meuble": (20, 150), "deco": (5, 50),
    "livre": (2, 15), "jeu_video": (5, 60), "vinyle_cd": (3, 25),
    "carte_collection": (5, 80), "figurine": (5, 80), "jouet": (5, 50),
    "outil": (10, 60), "cuisine": (5, 40), "sport_loisir": (25, 250),
    "autre": (5, 50),
}

# état -> multiplicateur des deux bornes
_MULT_ETAT = {"neuf": 1.7, "excellent": 1.35, "bon": 1.0, "correct": 0.7, "use": 0.5, "hs": 0.3}

# mots que le petit modèle peut écrire à la place d'un champ réellement vide
_MOTS_VIDE = {"vide", "inconnu", "inconnue", "n/a", "na", "none", "null", "aucun", "aucune", "/"}

# --- fourchettes par objet précis (mots-clés, priorité sur la catégorie) --
# Les grosses classes type "sport_loisir" ne peuvent pas donner un prix :
# une moto ne vaut pas comme une raquette. Ces surdéfixes répondent aux
# objets les plus courants ; la fourchette de catégorie reste le repli,
# et le prix proposé par le modèle a toujours le dernier mot dans son
# bandeau de vraisemblance (voir enrichir()).
_FOURCHETTES_SPECIFIQUES = [
    ("moto", (900, 4500)),
    ("scooter", (450, 2800)),
    ("apple pencil", (40, 160)),
    ("iphone", (80, 650)),
    ("galaxy", (60, 500)),
    ("pixel ", (60, 500)),
    ("telephone", (50, 500)),
    ("macbook", (350, 1400)),
    ("ordinateur", (180, 1200)),
    ("laptop", (180, 1200)),
    ("ipad", (140, 850)),
    ("playstation", (90, 420)),
    ("ps4", (70, 250)),
    ("ps5", (180, 480)),
    ("xbox", (70, 350)),
    ("switch", (100, 320)),
    ("console", (60, 400)),
    ("rolex", (1500, 9000)),
    ("omega", (500, 3000)),
    ("cartier", (600, 4000)),
    ("velo", (80, 900)),
    ("vtt", (80, 900)),
    ("trottinette", (90, 650)),
    ("guitare", (70, 1100)),
    ("piano", (150, 2500)),
    ("appareil photo", (70, 900)),
    ("reflex", (70, 900)),
    ("objectif", (40, 700)),
    ("drone", (70, 900)),
]


def _sans_accents(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texte.lower()) if not unicodedata.combining(c)
    )


def deviner_categorie(objet: str, mots_cles: str, marque: str) -> str:
    """Catégorie = 1er motif reconnu dans objet/mots-clés/marque."""
    hay = _sans_accents(f"{objet} {mots_cles} {marque}")
    for categorie, motifs in _MOTS_CLES_CATEGORIE:
        for motif in motifs:
            if _sans_accents(motif) in hay:
                return categorie
    return "autre"


def titre_annonce(ident: dict) -> str:
    """Titre court pour annonce/UI ; évite les doublons marque/objet."""
    objet = (ident.get("objet") or "").strip()
    marque = (ident.get("marque") or "").strip()
    modele = (ident.get("modele") or "").strip()
    base = objet.lower()
    prefixe = []
    if marque and marque.lower() not in base:
        prefixe.append(marque)
    if (
        modele
        and modele.lower() not in base
        and modele.lower() not in marque.lower()
    ):
        prefixe.append(modele)
    morceaux = prefixe + ([objet] if objet else [])
    titre = " ".join(m for m in morceaux if m).strip() or "Objet d'occasion"
    if len(titre) > 65:
        titre = titre[:62].rstrip() + "…"
    return titre


def enrichir(ident: dict) -> dict:
    """Complète l'identifications du modèle : categorie/rarete/valeurs/description.

    Les champs "vision" (texte_visible, objet, marque, modele, etat,
    mots_cles, confiance) viennent du modèle et sont préservés.
    """
    objet = (ident.get("objet") or "").strip()
    marquee_brute = (ident.get("marque") or "").strip()
    modele_brut = (ident.get("modele") or "").strip()
    texte_brut = (ident.get("texte_visible") or "").strip()
    # le petit modèle copie parfois le mot "vide" du gabarit JSON au lieu
    # de laisser la chaîne vide → nettoyage explicite
    for cle, valeur in (
        ("marque", marquee_brute),
        ("modele", modele_brut),
        ("texte_visible", texte_brut),
    ):
        if valeur.lower().strip(".,;") in _MOTS_VIDE:
            ident[cle] = ""
    marque = (ident.get("marque") or "").strip()
    modele = (ident.get("modele") or "").strip()
    ident["texte_visible"] = texte_brut if texte_brut.lower() not in _MOTS_VIDE else ""

    etat = (ident.get("etat") or "bon").strip().lower()
    mots_cles = (ident.get("mots_cles") or "").strip()
    confiance = min(1.0, max(0.0, float(ident.get("confiance") or 0.5)))

    categorie = deviner_categorie(objet, mots_cles, marque)
    if categorie not in _CATEGORIES_CONNUES:      # le modèle a fourni une catégorie valide ?
        categorie = ident.get("categorie") if ident.get("categorie") in _CATEGORIES_CONNUES else "autre"

    hay = _sans_accents(f"{objet} {mots_cles} {marque}")
    bornes = _FOURCHETTES.get(categorie, _FOURCHETTES["autre"])
    for motif, specifique in _FOURCHETTES_SPECIFIQUES:
        if motif in hay:
            bornes = specifique
            break
    mult = _MULT_ETAT.get(etat, 1.0)
    # une marque clairement lisible se revend mieux, sur toutes les catégories
    if marque and confiance >= 0.85:
        mult *= 1.35

    # Le modèle connaît le marché : sa fourchette prime si elle est
    # vraisemblable (ni 2 € pour une moto, ni 9 000 € pour un t-shirt).
    p_min = int(ident.get("prix_min") or 0)
    p_max = int(ident.get("prix_max") or 0)
    if p_min > 0 and p_max >= p_min \
            and p_min >= max(1, round(bornes[0] * 0.2)) \
            and p_max <= bornes[1] * 8:
        vmin = max(1, p_min)
        vmax = max(vmin + 2, p_max)
    else:
        vmin = max(1, round(bornes[0] * mult))
        vmax = max(vmin + 2, round(bornes[1] * mult))

    if marque and confiance >= 0.9 and categorie in {"carte_collection", "figurine"}:
        rarete = "rare"
    elif marque or confiance >= 0.8:
        # montre/jeu/livres/vinyles de marque : intéressants pour les initiés,
        # mais "rare" est réservé aux vraies pièces (cartes, figurines cotées)
        rarete = "interessant"
    else:
        rarete = "commun"

    titre = titre_annonce(dict(ident))
    # le modèle cloud a rédigé un paragraphe d'annonce naturel : il remplace
    # le gabarit sec ; sinon description = titre + état + texte visible
    annonce_modele = (ident.get("annonce") or "").strip()
    if annonce_modele:
        ident["description"] = annonce_modele
    else:
        texte_visible = (ident.get("texte_visible") or "").strip()
        description = f"{titre} en état {etat}."
        description += (
            f" Texte visible sur l'objet : {texte_visible}."
            if texte_visible
            else " Aucun texte lisible sur l'objet."
        )
        ident["description"] = description

    ident["categorie"] = categorie
    ident["rarete"] = rarete
    ident["valeur_min_eur"] = vmin
    ident["valeur_max_eur"] = vmax
    return ident
