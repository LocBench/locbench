#!/usr/bin/env bash
# reproduce.sh — everything the README promises, in one command.
#
#   bin/reproduce.sh
#
# It fetches the pinned engine sources, reruns the analyses, checks the chart
# and the card, runs both gates and the tests. No number is taken on trust.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() {
    printf '\n=== %s ===\n' "$1"
}

step "the pinned engine sources"
bin/fetch-sources.sh

step "the September analysis"
python3 bench/analyze_log.py --log data/2026-09-usage.jsonl

step "the four engines, one clock"
python3 bench/compare_engines.py --cell stream \
    data/2026-10-03-stream-ollama.jsonl \
    data/2026-10-03-stream-llamacpp.jsonl \
    data/2026-10-03-stream-tabbyapi.jsonl \
    data/2026-10-03-stream-lmstudio.jsonl

step "the chart and the card"
python3 bench/plot_fixed_cost.py --check
python3 bench/plot_social_preview.py --check

step "the fifth engine"
python3 bench/plot_fixed_cost_five.py --check

step "the gate on the pieces"
python3 bin/verify_piece.py --all

step "the post lengths"
python3 bin/verify_post.py --all

step "the tests"
python3 -m pytest tests/ -q

printf '\nEverything reproduced.\n'
