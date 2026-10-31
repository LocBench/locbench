#!/usr/bin/env bash
# run_hyperqwen.sh — the D4 campaign: the same streamed cell on the fifth engine.
#
# Run this on the host, where the Docker socket lives. The container must be up:
#
#   cd ~/tools/HyperQwen && docker compose --profile single up -d
#
# Then:
#
#   bash ~/Claude/LocBench/bench/run_hyperqwen.sh
#
# The API key is read from the container's .env and never printed. The seven
# lengths are the same ones the 3 October campaign used; the client warms up
# before it records anything.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${HYPERQWEN_ENV:-$HOME/tools/HyperQwen/.env}"
URL="${HYPERQWEN_URL:-http://127.0.0.1:18020}"

[ -f "$ENV_FILE" ] || {
    echo "no HyperQwen .env at $ENV_FILE" >&2
    exit 1
}
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
: "${VLLM_API_KEY:?VLLM_API_KEY is empty in $ENV_FILE}"

if ! curl -fsS --max-time 5 "$URL/health" >/dev/null 2>&1; then
    echo "HyperQwen is not answering at $URL" >&2
    echo "start it on the host: cd ~/tools/HyperQwen && docker compose --profile single up -d" >&2
    exit 1
fi

MODEL=$(curl -fsS --max-time 10 -H "Authorization: Bearer $VLLM_API_KEY" \
    "$URL/v1/models" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d["data"][0]["id"])
')
echo "  hyperqwen at $URL"
echo "  model: $MODEL"
echo "  key: present, not printed"
echo

DATE=$(date +%F)
OUT="data/${DATE}-stream-hyperqwen.jsonl"
CARD="data/${DATE}-environment-hyperqwen.txt"

python3 bench/measure.py --engine hyperqwen --url "$URL" --model "$MODEL" \
    --lengths 20,60,150,300,1200,2000,4000 \
    --repetitions 3 --stream --max-tokens 64 \
    --out "$OUT" sweep

bash bench/environment.sh > "$CARD"
echo
echo "  wrote $OUT"
echo "  wrote $CARD"
echo "  stop the container when you are done:"
echo "    cd ~/tools/HyperQwen && docker compose --profile single down"
