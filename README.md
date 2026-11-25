# BrocScan

> Historique des versions : voir `CHANGELOG.md` — copies archivées dans
> `~/brocscan-versions/` (une par numéro). Nouvelle version :
> `./scripts/nouvelle_version.sh 1.1 "ce qui change"`.

Photographiez un objet (1 à 3 photos, précisions optionnelles) → identification,
fourchette de valeur, et **annonces prêtes à coller** sur chaque plateforme.

Deux moteurs de vision (choix par défaut : **CLOUD d'abord**) :
- **CLOUD** : `glm-5.3-flash:cloud` (GPU distant relié à ton Ollama) —
  **2-5 s par scan**, bien plus précis sur l'identification d'objets ;
- **LOCAL en repli automatique** : gemma4:e2b (~20-30 s), si le cloud est
  injoignable (Wi-Fi coupé, quota…). Pour 100 % local : `VISION_CLOUD=0 ./run.sh`.

## Démarrer

```bash
./run.sh               # puis ouvrir http://localhost:8000
```

Depuis le téléphone (même Wi-Fi) : ouvrir `http://<ip-du-pc>:8000`.
Trouvez l'IP avec `hostname -I`. L'app est une PWA : « Ajouter à l'écran
d'accueil » pour l'utiliser comme une vraie app.

Modèles installés localement (le repli) :

```bash
ollama pull gemma4:e2b     # ~4.6 Go, une seule fois
```

## Comment ça marche

```
1-3 photos ──► app/images.py     décodage universel (WebP/HEIC...) + resize
   +           ──► app/vision.py     moteur CLOUD puis LOCAL : texte/objet/
   contexte                          marque/état + fourchette en JSON court
               ──► app/estimateur.py catégorie / fourchette / rareté /
                                     texte d'annonce calculés en PYTHON
                                     (zéro jeton = zéro temps)
               ──► app/market.py     par plateforme : titre + description
                                     d'annonce prêts à coller, lien du
                                     formulaire de dépôt, lien « ventes
                                     terminées » eBay (prix réellement payés)
               ──► app/db.py         historique (SQLite + photos dans data/)
```

- **Vitesse** : cloud ~2-5 s (mesuré) ; local ~20-30 s par photo une fois le
  modèle en RAM (keep_alive 4 h ; chargement à froid : 2-3 min). Le modèle
  produit un JSON minimal ; tout le reste est calculé en Python.
- **Précisions du vendeur** : le champ « PRÉCISIONS » est croisé avec la
  photo (la photo reste la référence en cas de contradiction).
- **Boîtes / emballages** : identification du PRODUIT contenu (l' Apple
  Pencil en boîte est reconnu direct par le cloud). 
- **Moteur par moteur** (`identification.moteur` + badges UI) : transparent
  sur le choix effectué.
- **Annonces** : les marketplaces n'autorisent ni le pré-remplissage externe
  de leur formulaire ni le dépôt automatisé — l'app réduit donc le
  copier-coller à deux clics (« Copier la description » → « Ouvrir le
  formulaire »). Liens de dépôt vérifiés : Leboncoin `/deposer-une-annonce`,
  Vinted `/items/new`, eBay `/sl/sell`.
- **Fourchettes** : prix proposé par le modèle + tables par mots-clés
  (moto, iPhone, PS5, Rolex…) × état × marque en app/estimateur.py,
  avec bandeaux de vraisemblance ; le prix réel se vérifie via le lien
  eBay « ventes terminées ».

## Limites connues

- Le cloud dépend d'un compte/quotas ollama.com côté Ollama ; les échecs
  replient sur le local sans intervention.
- Formats photo : décodage/re-encodage JPEG par app/images.py (JPEG, PNG,
  WebP, HEIC iPhone, GIF, BMP) ; on juge sur le contenu, pas sur le type.
- **gemma4:e4b inutilisable** sur l'Ollama installé (0.40.18) : erreur
  `Gemma4Assistant requires ctx_other to be set` (llama.cpp trop vieux).
- **qwen3-vl:4b local : trop lent sur CPU** (~1 token/s, réflexion par
  défaut impossible à couper sur cette version — /no_think ignoré) :
  5-7 min par scan. minicpm-v4.6 : marche mais qualité d'objet insuffisante.
  → candidats écartés ; le cloud joue ce rôle mieux qu'eux.
- Le serveur sert toutes les routes via un pool de threads (la route scan
  est synchrone) : une analyse longue ne bloque pas le reste de l'interface.

## Structure

```
app/main.py       API FastAPI (+ sert la page web)
app/vision.py     moteurs vision (cloud d'abord, local en repli) -> JSON court
app/estimateur.py catégorie, fourchette, rareté, texte d'annonce, titre (Python)
app/market.py     plateformes + liens dépôt/recherche + textes par site
app/images.py     normalisation des photos (formats, EXIF, resize)
app/db.py         SQLite, historique
static/           interface (aucune dépendance JS)
data/             photos + brocscan.db (créés à l'usage)
`.env` non requis : tout passe par run.sh (VISION_CLOUD, VISION_MODELES_CLOUD,
VISION_MODELE).
```

## Remise à zéro

```bash
rm -rf data        # vide historique et photos
```

