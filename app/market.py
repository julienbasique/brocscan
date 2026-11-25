"""Marché & revente : plateformes + TEXTES D'ANNONCE prêts à poster.

Deux services distincts :
  1. recommander_plateformes(ident) — pour chaque plateforme conseillée :
     - un lien "recherche" (ventes terminées eBay pour vérifier les comps),
     - un lien "déposer une annonce" (formulaire du site, URLs vérifiées),
     - un TITRE et une DESCRIPTION d'annonce adaptés au ton du site :
       le vendeur ouvre le formulaire, colle, vérifie, publie.
     (Les marketplaces n'autorisent pas le pré-remplissage externe de leur
     formulaire ni le dépôt automatisé — on ramène le copier-coller à
     deux clics, rien de plus.)
  2. Les fourchettes de prix sont générées par app/estimateur.py ; ici on
     les reprend telles quelles dans les textes.
"""
from urllib.parse import quote_plus

import re

from .estimateur import titre_annonce as _titre

# --- URLs (recherche = comps ; vendre = formulaire de dépôt, vérifiés) ---

def _ebay_recherche(mots_cles: str) -> str:
    # LH_Sold=1 + LH_Complete=1 : annonces écoulées (prix réellement payés)
    return (
        "https://www.ebay.fr/sch/i.html?_nkw=" + quote_plus(mots_cles)
        + "&LH_Sold=1&LH_Complete=1"
    )

def _vinted_recherche(mots_cles: str) -> str:
    return "https://www.vinted.fr/catalog?search_text=" + quote_plus(mots_cles)

def _leboncoin_recherche(mots_cles: str) -> str:
    return "https://www.leboncoin.fr/recherche?text=" + quote_plus(mots_cles)

def _catawiki_recherche(mots_cles: str) -> str:
    return "https://www.catawiki.fr/s?q=" + quote_plus(mots_cles)

# Registre des plateformes. "vendre" = formulaire de dépôt d'annonce
# (https://www.leboncoin.fr/deposer-une-annonce, https://www.vinted.fr/items/new,
# https://www.ebay.fr/sl/sell). Catawiki : pas de formulaire public simple → None.
_PLATEFORMES = {
    "vinted": {
        "recherche": _vinted_recherche,
        "vendre": "https://www.vinted.fr/items/new",
        "conseil": "Aucune commission vendeur, idéale mode & marque.",
    },
    "leboncoin": {
        "recherche": _leboncoin_recherche,
        "vendre": "https://www.leboncoin.fr/deposer-une-annonce",
        "conseil": "Vente locale, échange en main propre, univers complet.",
    },
    "ebay": {
        "recherche": _ebay_recherche,
        "vendre": "https://www.ebay.fr/sl/sell",
        "conseil": "Envoi national/international, vérifiez les prix via ventes terminées.",
    },
    "catawiki": {
        "recherche": _catawiki_recherche,
        "vendre": None,
        "conseil": "Collection & luxe : enchères supervisées, meilleur prix.",
    },
}

# catégorie -> plateformes recommandées (dans l'ordre)
PLATEFORMES_PAR_CATEGORIE = {
    "vetement": ["vinted", "leboncoin"],
    "chaussures": ["vinted"],
    "sac": ["vinted", "catawiki"],
    "montre_bijou": ["catawiki", "ebay"],
    "electronique": ["leboncoin", "ebay"],
    "electromenager": ["leboncoin"],
    "meuble": ["leboncoin"],
    "deco": ["catawiki", "leboncoin"],
    "livre": ["leboncoin", "ebay"],
    "jeu_video": ["leboncoin", "ebay"],
    "vinyle_cd": ["ebay", "catawiki"],
    "carte_collection": ["ebay", "catawiki"],
    "figurine": ["ebay", "catawiki"],
    "jouet": ["leboncoin", "ebay"],
    "outil": ["leboncoin"],
    "cuisine": ["leboncoin", "catawiki"],
    "sport_loisir": ["leboncoin"],
    "autre": ["leboncoin", "ebay"],
}


# --- Titre & textes d'annonce -------------------------------------------
# (le titre vient de estimateur.titre_annonce, importé en tête de fichier)

_ETATS_FR = {
    "neuf": "neuf",
    "excellent": "excellent état",
    "bon": "bon état",
    "correct": "état correct",
    "use": "visiblement usé",
    "hs": "hors service (pour pièces ou débrouillard)",
}


def _lisible_net(ident: dict) -> str:
    """texte_visible lisible pour UN HUMAIN : sans « photoN: », sans doublons."""
    brut = (ident.get("texte_visible") or "").strip()
    if not brut:
        return ""
    vus: list[str] = []
    for morceau in brut.split(" | "):
        net = re.sub(r"^photo\s*\d+\s*:\s*", "", morceau.strip())
        if net and net.lower() not in [v.lower() for v in vus]:
            vus.append(net)
    return " ; ".join(vus)


def _annonces_par_site(ident: dict, titre: str) -> dict[str, str]:
    """Texte d'annonce par plateforme (ton adapté, prêt à coller).

    Pro : le paragraphe descriptif vient du modèle (ident["annonce"]), la
    préparation Python ajoute les SECTIONS utiles (état, inscriptions,
    envoi) — jamais de prix dans le texte (le prix se règle dans le champ
    dédié du site ; une fourchette dans le texte fait amateur).
    """
    etat_fr = _ETATS_FR.get(ident.get("etat") or "bon", "bon état")
    lisible_net = _lisible_net(ident)
    rarete = ident.get("rarete") or "commun"

    noyau_lignes = [(ident.get("annonce") or "").strip()]
    if etat_fr and not any(
        m in (noyau_lignes[0] or "").lower() for m in ("état", "l'état", "usé")
    ):
        noyau_lignes.append(f"État : {etat_fr}.")
    if lisible_net:
        noyau_lignes.append(f"Marquages lisibles : {lisible_net}.")
    if rarete == "rare":
        noyau_lignes.append("Pièce recherchée par les collectionneurs.")
    noyau = "\n".join(l for l in noyau_lignes if l) or (
        f"{titre} — {etat_fr}."
    )

    leboncoin = "\n".join(
        t for t in (
            noyau,
            "Prix négociable en cas d'achat groupé.",
            "Remise en main possible ou envoi colis suivi, bien protégé. "
            "Réponse rapide à toute question.",
        ) if t
    )

    # Vinted : tutoiement, court, SANS prix (champ dédié sur le site)
    vinted = "\n".join(
        t for t in (
            noyau,
            "Photos réelles du bien, vendu tel quel. N'hésite pas à me demander d'autres photos !",
        ) if t
    )

    # eBay : le prix se règle dans le formulaire — pas de mention de prix ici
    ebay = "\n".join(
        t for t in (
            noyau,
            "Envoi colis suivi avec emballage rigide. Questions bienvenues, réponse rapide.",
        ) if t
    )

    return {"leboncoin": leboncoin, "vinted": vinted, "ebay": ebay}


# --- API du module -------------------------------------------------------

def recommander_plateformes(ident: dict) -> list[dict]:
    """Liste ordonnée de plateformes avec liens + textes d'annonce prêts.

    Chaque entrée : {nom, conseil, url_recherche, url_vendre, titre, description}.
    url_vendre est None si la plateforme n'a pas de formulaire public simple.
    """
    mots_cles = ident.get("mots_cles") or ident.get("objet") or ""
    categorie = ident.get("categorie", "autre")
    titre = _titre(ident)
    textes = _annonces_par_site(ident, titre)

    cles = PLATEFORMES_PAR_CATEGORIE.get(categorie) or PLATEFORMES_PAR_CATEGORIE["autre"]
    noms_affiches = {"vinted": "Vinted", "leboncoin": "Leboncoin", "ebay": "eBay FR", "catawiki": "Catawiki"}
    liens = []
    for cle in cles:
        pf = _PLATEFORMES[cle]
        liens.append(
            {
                "nom": noms_affiches[cle],
                "conseil": pf["conseil"],
                "url_recherche": pf["recherche"](mots_cles),
                "url_vendre": pf["vendre"],
                "titre": titre,
                # texte adapté au site, sinon repli générique style eBay
                "description": textes.get(cle) or textes["ebay"],
            }
        )
    return liens
