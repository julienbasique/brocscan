"""Base de données BrocScan — SQLite tout simple, sans ORM pour rester lisible.

Schéma de la table `scans` :
    id          identifiant aléatoire (sert aussi de nom de fichier photo)
    created_at  date ISO
    photo_path  chemin relatif de la photo enregistrée (depuis data/)
    ident       JSON brut renvoyé par l'étape vision (objet, marque, ...)
    v_min/v_max fourchette d'estimation IA en euros
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "brocscan.db"


def _connexion() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _connexion() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS scans (
                id          TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                photo_path  TEXT NOT NULL,
                ident       TEXT NOT NULL,
                v_min       REAL,
                v_max       REAL
            )"""
        )


def save_scan(scan_id: str, photo_path: str, ident: dict) -> str:
    """Enregistre un scan ; retourne l'id."""
    with _connexion() as con:
        con.execute(
            "INSERT INTO scans (id, created_at, photo_path, ident, v_min, v_max) VALUES (?, ?, ?, ?, ?, ?)",
            (
                scan_id,
                # heure locale (l'historique est affiché tel quel côté front)
                datetime.now().isoformat(timespec="seconds"),
                photo_path,
                json.dumps(ident, ensure_ascii=False),
                ident.get("valeur_min_eur"),
                ident.get("valeur_max_eur"),
            ),
        )
    return scan_id


def list_scans(limit: int = 50) -> list[dict]:
    with _connexion() as con:
        lignes = con.execute(
            "SELECT * FROM scans ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    resultats = []
    for row in lignes:
        resultats.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "photo": "/photo/" + row["id"],
                **json.loads(row["ident"]),
            }
        )
    return resultats


def delete_scan(scan_id: str) -> bool:
    """Supprime une entrée et ses photos (y compris photos 2-3) ; True si existait."""
    with _connexion() as con:
        row = con.execute(
            "SELECT photo_path FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
        if row is None:
            return False
        con.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    photo = DATA_DIR / row["photo_path"]
    photo.unlink(missing_ok=True)
    # photos supplémentaires d'un scan multi-photos : {id}_2.jpg, {id}_3.jpg...
    for extra in (DATA_DIR / "photos").glob(f"{scan_id}_*.jpg"):
        extra.unlink(missing_ok=True)
    return True


def photo_path_of(scan_id: str) -> Path | None:
    with _connexion() as con:
        row = con.execute(
            "SELECT photo_path FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
    return (DATA_DIR / row["photo_path"]) if row else None
