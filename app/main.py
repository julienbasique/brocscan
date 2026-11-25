"""Serveur BrocScan — FastAPI.

Routes :
    GET  /                interface web (static/index.html)
    POST /api/scan        photo multipart -> identification + plateformes
    GET  /api/scans       historique
    DELETE /api/scans/{id}  supprimer une entrée
    GET  /api/status      état d'Ollama et du modèle
    GET  /photo/{id}      renvoyer la photo enregistrée
"""
import base64
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from requests import RequestException

from . import db, vision
from .images import normaliser_image
from .market import recommander_plateformes
from .marche import prix_reels_vinted
from .public import CODE_ACCES, PUBLIC, verifier as verifier_limite

BASE = Path(__file__).resolve().parent.parent
app = FastAPI(title="BrocScan", version="1.2.0")
db.init_db()
(BASE / "data").mkdir(exist_ok=True)


@app.post("/api/scan")
def scan(
    request: Request,
    photos: list[UploadFile] = File(...),
    contexte: str = Form(""),
):
    """Pipeline : 1-3 photos (+ contexte optionnel) -> Gemma 4 -> annonces -> sauvegarde.

    Les photos montrent le MÊME objet sous plusieurs angles ; la première
    fait foi. Le contexte est une phrase libre du vendeur (« boîte Apple
    Pencil », « vendu avec étui »...) croisée avec la photo.

    Route synchrone (def, pas async) : FastAPI l'exécute dans un pool de
    threads, sinon l'appel bloquant vers Ollama (plusieurs minutes sur CPU)
    gèlerait TOUT le serveur (historique, /photo...) pendant une analyse.
    """
    verifier_limite("scan", request)      # mode public : quotas (sinon sans effet)
    if not photos or not photos[0].filename:
        raise HTTPException(400, "au moins une photo est requise")
    photos = photos[:3]                     # 3 photos max, même objet

    normales = []
    for i, fichier in enumerate(photos):
        octets = fichier.file.read()
        if len(octets) > 15_000_000:
            raise HTTPException(413, f"photo {i + 1} trop lourde (max 15 Mo)")
        try:
            # la 1re photo à pleine résolution (identification + lecture du
            # texte) ; les suivantes réduites : le prompt image coûte cher
            # en CPU et les angles complémentaires supportent moins de détails
            taille = (1600, 1600) if i == 0 else (1024, 1024)
            normales.append(normaliser_image(octets, taille))
        except ValueError:
            raise HTTPException(
                400, f"photo {i + 1} ni image, ni décodable (attendu : JPG/PNG/WebP/HEIC)"
            )

    indice = (contexte or "").strip()
    try:
        ident = vision.identifier(normales, contexte=indice)
    except json.JSONDecodeError as e:
        raise HTTPException(502, f"réponse du modèle inexploitable : {e}")
    except ValueError as e:
        # réponse tronquée / JSON non terminé
        raise HTTPException(502, f"réponse du modèle tronquée — réessayez ({e})")
    except RuntimeError as e:            # modèle absent / image refusée
        raise HTTPException(400 if "refusé" in str(e) else 503, str(e))
    except RequestException as e:        # Ollama injoignable / timeout
        raise HTTPException(503, f"Ollama injoignable : {e}")

    scan_id = uuid.uuid4().hex[:12]
    if PUBLIC:
        # Démo : scan ÉPHÉMÈRE — rien sur le disque, rien dans l'historique
        # de Julien (data/ est SON espace). Le visiteur voit immédiatement
        # son résultat (photo rendue en data URI), c'est tout.
        uris = ["data:image/jpeg;base64," + base64.b64encode(b).decode()
                for b in normales]
        return {
            "id": scan_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "photo": uris[0],
            "photos_extra": uris[1:],
            "contexte": indice,
            "identification": ident,
            "plateformes": recommander_plateformes(ident),
        }
    dossier = BASE / "data" / "photos"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{scan_id}.jpg").write_bytes(normales[0])
    photos_extra = []
    for numero, octets_img in enumerate(normales[1:], start=2):
        (dossier / f"{scan_id}_{numero}.jpg").write_bytes(octets_img)
        photos_extra.append(f"/photo/{scan_id}/{numero}")

    db.save_scan(scan_id, f"photos/{scan_id}.jpg", ident)
    return {
        "id": scan_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "photo": "/photo/" + scan_id,
        "photos_extra": photos_extra,
        "contexte": indice,
        "identification": ident,
        "plateformes": recommander_plateformes(ident),
    }


@app.get("/api/scans")
def historique():
    if PUBLIC:
        # la démo internet ne montre JAMAIS les scans de Julien
        return []
    return db.list_scans()


@app.delete("/api/scans/{scan_id}")
def supprimer(scan_id: str):
    if PUBLIC:
        raise HTTPException(403, "Indisponible sur la démo publique")
    if not db.delete_scan(scan_id):
        raise HTTPException(404, "scan inconnu")
    return {"ok": True}


@app.get("/api/marche")
def marche(mots_cles: str, request: Request,
           v_min: float | None = None, v_max: float | None = None):
    """Prix RÉELS du marché d'occasion (Vinted, via Chrome réel).

    À la demande (bouton de l'interface) : un scan ne déclenche jamais
    cette navigation, elle coûte ~10-20 s. Si la fourchette IA du dernier
    scan est passée (v_min/v_max), le résultat porte un ANCRAGE : le prix
    conseillé = médiane des vraies annonces (le marché est le juge).
    """
    verifier_limite("marche", request)    # mode public : quotas (sinon sans effet)
    if not mots_cles.strip():
        raise HTTPException(400, "mots_clés manquants")
    result = prix_reels_vinted(mots_cles.strip())
    if (result.get("ok") and v_min is not None and v_max is not None
            and v_max >= v_min > 0):
        med = result.get("mediane") or 0
        if med <= 0:
            return result
        result["prix_conseille"] = med
        if v_min <= med <= v_max:
            result["ancrage"] = "médiane du marché, dans ta fourchette"
        elif med < v_min:
            result["ancrage"] = "le marché est MOINS cher que ton estimation"
        else:
            result["ancrage"] = "le marché est PLUS cher que ton estimation"
    return result


@app.get("/api/status")
def statut():
    return {
        "ollama_actif": vision.modele_disponible(),
        "modele": vision.MODELE,
        "cloud": vision.ACTIVER_CLOUD,
        "modeles_cloud": vision.MODELES_CLOUD,
        "public": PUBLIC,
        "code_requis": bool(CODE_ACCES),
    }


@app.get("/photo/{scan_id}")
def image(scan_id: str):
    if PUBLIC:
        # démo internet : les photos enregistrées de Julien restent privées
        raise HTTPException(404, "photo inconnue")
    chemin = db.photo_path_of(scan_id)
    if chemin is None:
        raise HTTPException(404, "photo inconnue")
    return FileResponse(chemin, media_type="image/jpeg")


@app.get("/photo/{scan_id}/{numero}")
def image_supplementaire(scan_id: str, numero: int):
    """Photo 2 ou 3 d'un scan multi-photos (photos/{id}_{n}.jpg)."""
    if PUBLIC:
        raise HTTPException(404, "photo inconnue")
    if numero < 2 or numero > 5:
        raise HTTPException(404, "photo inconnue")
    chemin = BASE / "data" / "photos" / f"{scan_id}_{numero}.jpg"
    if not chemin.is_file():
        raise HTTPException(404, "photo inconnue")
    return FileResponse(chemin, media_type="image/jpeg")


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/", include_in_schema=False)
def racine():
    return FileResponse(BASE / "static" / "index.html")
