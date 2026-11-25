#!/bin/bash
# Banc de verification BrocScan — à lancer après CHAQUE changement du code.
# Coût : ~2 scans nuage (quelques secondes) + navigations Chrome ÉVITÉES
# (le banc ne parle pas à Vinted). Couvre ce que le bug v1.3 a révélé :
# les DEUX instances, les gates publics, la privée SANS plafond.
set -u
PCD=/home/julien/brocscan
BIN="$PCD/.venv/bin"
PHOTO="$PCD/data/photos/834292e09e6d.jpg"     # vraie photo de test (DualSense)
ERREURS=0
fail() { echo "✘ $1"; ERREURS=$((ERREURS+1)); }
ok()   { echo "✔ $1"; }

echo "== 1. Production (privée 8000 / publique 8001) =="
curl -s -m 5 http://localhost:8000/api/status | grep -q ollama_actif && ok "privée :8000 répond" || fail "privée :8000"
curl -s -m 5 http://127.0.0.1:8001/api/status | grep -q '"public":true' && ok "publique :8001 répond (public:true)" || fail "publique :8001"
curl -s -m 5 http://localhost:8000/api/scans | grep -q '\[' && ok "historique VISIBLE sur privée" || fail "historique privée"
[ "$(curl -s -m 8 http://127.0.0.1:8001/api/scans)" = "[]" ] && ok "historique MASQUÉ sur publique" || fail "historique public"
[ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8001/photo/xxx)" = "404" ] && ok "photos privées bloquées (404)" || fail "photos publiques"
[ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' -X DELETE http://127.0.0.1:8001/api/scans/xxx)" = "403" ] && ok "suppression bloquée publique (403)" || fail "suppression publique"
curl -s -m 5 http://localhost:8000/api/stats | grep -q 'stats' && ok "/api/stats répond" || fail "/api/stats"
curl -s -m 5 http://localhost:8000/ | grep -q BrocScan && ok "page privée sert l'interface" || fail "page privée"
curl -s -m 10 -o /dev/null -w '%{http_code}' https://brocscan.tail598dc7.ts.net/api/status | grep -q 200 && ok "porte internet ouverte" || fail "porte internet"

echo "== 2. Instance jetable PUBLIC avec code + limite 1 (8012) =="
pkill -f '[u]vicorn app.main:app --host 127.0.0.1 --port 8012' 2>/dev/null; sleep 1
(cd "$PCD" && PUBLIC_DEMO=1 CODE_ACCES=test LIMITE_SCANS_HEURE=1 \
  VISION_CLOUD=1 VISION_MODELES_CLOUD="glm-5.3-flash:cloud" \
  "$BIN/uvicorn" app.main:app --host 127.0.0.1 --port 8012 >/tmp/bench8012.log 2>&1 &)
sleep 3
S=$(curl -s -o /dev/null -m 20 -w '%{http_code}' -F "photos=@$PHOTO" http://127.0.0.1:8012/api/scan)
[ "$S" = "401" ] && ok "scan SANS code refusé (401, pas de nuage burné)" || fail "gate code sans code (reçu $S)"
S=$(curl -s -o /dev/null -m 90 -w '%{http_code}' -F "photos=@$PHOTO" -H "x-code-acces: test" http://127.0.0.1:8012/api/scan)
[ "$S" = "200" ] && ok "scan AVEC code passé" || fail "scan avec code (reçu $S)"
S=$(curl -s -o /dev/null -m 20 -w '%{http_code}' -F "photos=@$PHOTO" -H "x-code-acces: test" http://127.0.0.1:8012/api/scan)
[ "$S" = "429" ] && ok "limite par heure appliquée (429)" || fail "limite horaire (reçu $S)"
pkill -f '[u]vicorn app.main:app --host 127.0.0.1 --port 8012' 2>/dev/null

echo "== 3. Instance jetable PRIVÉE (8013) : aucun plafond =="
pkill -f '[u]vicorn app.main:app --host 127.0.0.1 --port 8013' 2>/dev/null; sleep 1
(cd "$PCD" && VISION_CLOUD=1 VISION_MODELES_CLOUD="glm-5.3-flash:cloud" \
  "$BIN/uvicorn" app.main:app --host 127.0.0.1 --port 8013 >/tmp/bench8013.log 2>&1 &)
sleep 3
R=$(curl -s -m 90 -F "photos=@$PHOTO" http://127.0.0.1:8013/api/scan)
SID=$(echo "$R" | "$BIN/python" -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -n "$SID" ] && ok "scan privé : SANS code, SANS limite (v1.3-bug vérifié)" || fail "scan privé sans plafond"
[ -n "$SID" ] && curl -s -m 5 -X DELETE "http://127.0.0.1:8013/api/scans/$SID" >/dev/null && ok "scan de test nettoyé de l'historique" || fail "nettoyage scan de test"
pkill -f '[u]vicorn app.main:app --host 127.0.0.1 --port 8013' 2>/dev/null

echo
[ "$ERREURS" -eq 0 ] && echo "✅ TOUT EST OK" || echo "❌ $ERREURS échec(s) — corriger avant de livrer"
exit $ERREURS
