"""Normalisation des photos avant envoi à Ollama.

Le décodeur multimodal d'Ollama ne lit que certains conteneurs : les
variantes WebP/HEIC/AVIF (photo de téléphone) ont produit l'erreur
« failed to decode buffer as image ». On décode donc TOUT ici avec Pillow
(JPEG, PNG, WebP, GIF, BMP, HEIC via pillow-heif) et on ré-encode:

    - rotation corrigée (EXIF, photos de téléphone à l'horizontal);
    - converti en RVB ;
    - réduit à 1600 px max (prompt vision plus court -> scan plus rapide);
    - ré-encodé en JPEG propre, garanti décodable par Ollama.
"""
import io

from pillow_heif import register_heif_opener

# permet de lire les photos iPhone (.heic/.heif)
register_heif_opener()

from PIL import Image, ImageOps  # noqa: E402  (après register_heif_opener)

# limite d'encombrement envoyée au modèle (px)
_TAILLE_MAX = (1600, 1600)
_QUALITE_JPEG = 88


def normaliser_image(octets: bytes, taille_max: tuple | None = None) -> bytes:
    """Octets de photo (n'importe quel format courant) -> JPEG propre.

    taille_max : borne (l, h) optionnelle — par défaut _TAILLE_MAX. Les
    photos 2-3 d'un scan multi-photos passent une borne réduite : la
    préfection du prompt image coûte cher en CPU, la première photo (qui
    porte l'identification) reste à pleine résolution.

    Lève ValueError si la photo est indécodable par Pillow/pillow-heif.
    """
    try:
        image = Image.open(io.BytesIO(octets))
        image = ImageOps.exif_transpose(image)   # respecte l'orientation EXIF
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.thumbnail(taille_max or _TAILLE_MAX, Image.LANCZOS)

        sortie = io.BytesIO()
        image.save(sortie, format="JPEG", quality=_QUALITE_JPEG, optimize=True)
        return sortie.getvalue()
    except Exception as e:                       # indécodable ou corrompue
        raise ValueError(f"photo illisible ({e})") from e
