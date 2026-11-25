#!/bin/bash
# Nouvelle version BrocScan : enregistre l'état actuel comme une version.
# Usage : ./scripts/nouvelle_version.sh 1.1 "ce qui change en une phrase"
set -e
V="${1:?numéro de version, ex : 1.1}"
MSG="${2:?description courte de ce qui change}"
cd "$(dirname "$0")/.."

# 1) Historique technique (git) : tout le code, pas les photos/données
git add -A
git commit -m "v${V} — ${MSG}" || echo "(aucun changement de code à enregistrer)"
git tag -f "v${V}"

# 2) Copie archive visible : code + données de Julien (sans .venv, sans .git)
DEST="$HOME/brocscan-versions/brocscan-v${V}"
mkdir -p "$DEST"
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude '.git' --delete "${PWD}/" "$DEST/"

echo "✔ Version v${V} archivée : $DEST"
ls "$HOME/brocscan-versions/"
