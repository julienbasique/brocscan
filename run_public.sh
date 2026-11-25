#!/usr/bin/env bash
# Lance l'instance PUBLIQUE de BrocScan : démo internet sur le port 8001.
# Différences avec l'instance de Julien (run.sh) :
#   - PUBLIC_DEMO=1  → aucune photo/historique de Julien exposée + quotas
#                      (app/public.py : 4 scans/h/IP, 100/jour ; Vinted 1/h)
#   - VISION_CLOUD=1 → moteur nuage comme pour Julien (rapide, quota partagé
#                      mais plafonné par les quotas publics)
#   - écoute 127.0.0.1 seulement : nulle part à atteindre SAUF via la porte
#     Tailscale Funnel (voir ~/bin/lance_brocscan.sh).
exec env PUBLIC_DEMO=1 VISION_CLOUD=1 VISION_MODELES_CLOUD="glm-5.3-flash:cloud,gemma4:cloud" \
    ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
