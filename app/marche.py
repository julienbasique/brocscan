"""Marché RÉEL : prix d'occasion constatés via un vrai navigateur.

La demande de Julien : comparer l'estimation IA avec de VRAIS prix en ligne.
Les API publiques de Leboncoin/Vinted sont protégées (FraudShield) et eBay
bloque l'automatisation, mais la page de résultats Vinted rendue dans un
Chrome réel expose chaque annonce en attribut `title` :

    title="Manette DualSense blanche, État: Très bon état, 20.00 €, 21.70 €"

→ parsing trivial, indépendant des classes CSS (hachées et changeantes).

Lancement : bouton "Prix réels" de l'interface (à la demande, pas au scan,
pour garder l'analyse à 2 s). Ce sont des prix DEMANDÉS (pas encore vendus) :
les ventes réellement écoulées restent dans le lien eBay « ventes terminées ».
"""
import re
import statistics
from urllib.parse import quote_plus

# mots qui disqualifient une annonce (accessoires, pas l'objet lui-même)
_MOTS_EXCLUS = (
    "coque", "silicone", "grip", "caps", "joystick", "sticker", "protection",
    "kit ", "housse", "skin", "station de charge", "chargeur", "câble", "cable",
    "autocollant", "pochette", "étui", "etui", "cache", "décoration",
    "decoration", "bracelet montre", "livre ",
    # hors-sujet fréquents (fr-en, souvent en anglais sur Vinted)
    "boîte", "boite", "support", "batterie", "ps4", "ps3", "ps2", "ps5 pro",
    "+ 2", "+2", "console", "jeu ", "jeux", "fifa", "casque", "volant",
    "manette arcade", "stand", "mount", "holder", "dock", "accessories",
    "accessoire", "coque ps4", "cable ps",
)

_TIMEOUT_MS = 45_000


def _parse_annonce(attr_title: str) -> tuple[str, float] | None:
    """'Titre, État: Très bon état, 20.00 €, 21.70 € Frais Vinted inclus'
    -> (titre, 20.0). None si pas de prix lisible."""
    morceaux = [m.strip() for m in attr_title.split(",")]
    prix = None
    titre = []
    etat_vu = False
    for segment in morceaux:
        if etat_vu and prix is None:
            m = re.match(r"^(\d{1,4})(?:[.,](\d{1,2}))?\s*€$", segment)
            if m:
                prix = int(m.group(1)) + (int(m.group(2)) / 100 if m.group(2) else 0)
                continue
        if segment.lower().startswith("état:"):
            etat_vu = True
            continue
        if prix is None and not titre:
            titre.append(segment)
        elif prix is None:
            titre.append(segment)
    if prix is None or prix <= 0:
        return None
    return (" ".join(titre).strip(" ,"), prix)


def prix_reels_vinted(mots_cles: str, limite_annonces: int = 40) -> dict:
    """Ouvre un Chrome réel sur Vinted, lit les annonces, renvoie les stats.

    Retourne {ok, erreur?, nombre, min, mediane, max, echantillon: [(titre, prix)]}.
    """
    from playwright.sync_api import sync_playwright

    recherche = mots_cles.strip() or "dualsense"
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(channel="chrome", headless=False)
            page = nav.new_page(locale="fr-FR", viewport={"width": 1280, "height": 900})
            page.goto(
                f"https://www.vinted.fr/catalog?search_text={quote_plus(recherche)}",
                timeout=_TIMEOUT_MS,
            )
            page.wait_for_timeout(3500)
            for _ in range(2):
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(1000)
            annonces = page.evaluate(
                """() => Array.from(
                    document.querySelectorAll('a[data-testid$="--overlay-link"]')
                ).map(a => a.getAttribute('title') || '')"""
            )
            nav.close()
    except Exception as e:
        return {"ok": False, "erreur": f"navigateur indisponible : {str(e)[:150]}"}

    brutes = []
    for attr in annonces:
        if not attr:
            continue
        parse = _parse_annonce(attr)
        if parse:
            brutes.append(parse)

    # pertinence : le titre doit contenir un MOT-CLÉ substantif de la
    # recherche (≥4 lettres : "manette", "montre", "moto"...) — les mots
    # courts (ps5, 125) y laissent trop passer le hors-sujet
    mots = [w for w in _sans_accents(recherche).split() if len(w) >= 4]
    filtres = []
    for titre, prix in brutes:
        t = _sans_accents(titre)
        if any(x in t for x in _MOTS_EXCLUS):
            continue
        if mots and not any(m in t for m in mots):
            continue
        filtres.append((titre, round(prix)))

    if len(filtres) < 3:
        # trop peu de pertinents : revenir sur tout ce qui a un prix
        filtres = brutes if len(brutes) >= 5 else filtres

    if not filtres:
        return {
            "ok": False,
            "erreur": f"aucune annonce pertinente lue sur Vinted pour « {recherche} »",
            "source": "Vinted (prix demandés)",
        }

    prix_ = [p for _, p in filtres]
    echantillon = sorted(filtres, key=lambda x: x[1])
    milieu = len(echantillon) // 2
    return {
        "ok": True,
        "source": "Vinted — prix demandés, aujourd'hui",
        "nombre": len(filtres),
        "min": min(prix_),
        "mediane": round(statistics.median(prix_)),
        "max": max(prix_),
        "echantillon": [f"{t} — {p} €" for t, p in (
            echantillon[:2] + [echantillon[milieu]] + echantillon[-2:]
        )],
        "url": f"https://www.vinted.fr/catalog?search_text={quote_plus(recherche)}",
    }


def _sans_accents(texte: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFKD", texte.lower())
        if not unicodedata.combining(c)
    )


if __name__ == "__main__":     # test direct : python -m app.marche "manette ps5"
    import sys

    print(prix_reels_vinted(sys.argv[1] if len(sys.argv) > 1 else "dualsense"))
