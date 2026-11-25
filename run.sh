#!/usr/bin/env bash
# Lance le serveur BrocScan (http://localhost:8000)
# Mode par défaut : CLOUD d'abord (glm-5.3-flash:cloud chez Ollama.com,
# ~2-5 s/scan) + repli AUTOMATIQUE sur le gemma local si le cloud est
# injoignable (Wi-Fi coupé, quota...). Pour revenir au 100 % local :
# mettre VISION_CLOUD=0.
export VISION_CLOUD=1
export VISION_MODELES_CLOUD="glm-5.3-flash:cloud"
cd "$(dirname "$0")"
exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

