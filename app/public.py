"""Mode DÉMO PUBLIQUE : quotas simples anti-abus.

Activé par PUBLIC_DEMO=1 sur l'instance INTERNET (port 8001, lancée par
~/bin/lance_brocscan.sh + Tailscale Funnel). L'instance de Julien (port
8000) n'a JAMAIS de limites ni d'historique masqué : ses usages ne passent
pas par ici.

Pourquoi limiter : chaque scan public consomme le compte nuage Ollama de
Julien (qui a ses propres plafonds) et chaque recherche « prix réels »
ouvre une navigation Chrome depuis l'IP maison — des centaines par jour
feraient bannir l'IP par Vinted. Les compteurs vivent en mémoire : un
redémarrage les remet à zéro, ce n'est pas de l'audit, juste un tampon.
"""

import os
import threading
import time
from datetime import date

from fastapi import HTTPException, Request

CODE_ACCES = os.environ.get("CODE_ACCES", "").strip()

PUBLIC = os.environ.get("PUBLIC_DEMO") == "1"

# fenêtre glissante d'une heure + plafond global par jour (toutes IP)
# réglables par variables d'environnement (banc de tests, ajustements)
MAX_HEURE = {
    "scan": int(os.environ.get("LIMITE_SCANS_HEURE") or 4),
    "marche": int(os.environ.get("LIMITE_MARCHE_HEURE") or 1),
}
MAX_JOUR = {
    "scan": int(os.environ.get("LIMITE_SCANS_JOUR") or 100),
    "marche": int(os.environ.get("LIMITE_MARCHE_JOUR") or 12),
}

MESSAGES_HEURE = {
    "scan": f"Démo publique : maximum {MAX_HEURE['scan']} analyses/heure — réessayez dans un moment.",
    "marche": f"Démo publique : maximum {MAX_HEURE['marche']} recherche « prix réels »/heure — réessayez plus tard.",
}
MESSAGES_JOUR = {
    "scan": "Démo publique : le quota de la journée est épuisé — revenez demain.",
    "marche": "Démo publique : plus de recherche « prix réels » aujourd'hui — revenez demain.",
}

_VERROU = threading.Lock()
_FENETRE: dict[tuple[str, str], list[float]] = {}
_JOUR: dict[date, dict[str, int]] = {}


def verifier(cle: str, request: Request) -> None:
    """Lève HTTPException (si interdit/dépassement) ou note l'usage (sinon)."""
    if not PUBLIC:
        return        # l'instance privée de Julien n'a JAMAIS de limites

    transmise = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    ip = transmise or (request.client.host if request.client else "?")
    maintenant = time.time()
    avec_verrou = date.today()
    with _VERROU:
        # 1. code d'accès (optionnel : si CODE_ACCES est posé, il est exigé) ;
        #    un mauvais code ne consomme PAS la quota
        donne = request.headers.get("x-code-acces", "").strip()
        if CODE_ACCES and donne != CODE_ACCES:
            raise HTTPException(
                401,
                "Code d'accès requis — demandez-le au propriétaire de la démo.",
            )
        # 2. quotas
        fenetre = [t for t in _FENETRE.get((cle, ip), []) if maintenant - t < 3600]
        if len(fenetre) >= MAX_HEURE[cle]:
            raise HTTPException(429, MESSAGES_HEURE[cle])
        du_jour = _JOUR.get(avec_verrou, {}).get(cle, 0)
        if du_jour >= MAX_JOUR[cle]:
            raise HTTPException(429, MESSAGES_JOUR[cle])
        _FENETRE[(cle, ip)] = fenetre + [maintenant]
        _JOUR.setdefault(avec_verrou, {"scan": 0, "marche": 0})[cle] = du_jour + 1
        # garde-fou mémoire : on oublie les jours d'avant-hier
        if len(_JOUR) > 3:
            for vieux in sorted(_JOUR)[:-1]:
                _JOUR.pop(vieux, None)
