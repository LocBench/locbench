#!/bin/bash
# environment.sh — the card that every published number has to carry.
#
# The protocol says each measurement carries this. Without it a number cannot be
# attributed to anything: an engine update, a driver update or a different card
# all move the results, and none of them announce themselves in the data.
#
#     bash bench/environment.sh              # print the card
#     bash bench/environment.sh >> card.txt  # keep it beside a session
#
# Anything it cannot find it says so, rather than leaving a blank that reads as
# a zero.

set -uo pipefail

line() { printf '%-22s %s\n' "$1" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

echo "LocBench — environment"
line "captured" "$(date -Iseconds)"

# ---- the machine
if have nvidia-smi; then
    IFS=',' read -r name vram driver <<<"$(nvidia-smi --query-gpu=name,memory.total,driver_version \
        --format=csv,noheader 2>/dev/null | head -1)"
    line "gpu" "$(echo "$name" | sed 's/^ *//')"
    line "vram" "$(echo "$vram" | sed 's/^ *//')"
    line "driver" "$(echo "$driver" | sed 's/^ *//')"
    # What else is on the card. The protocol asks for no external load, and this
    # is how a reader can tell whether there was one.
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    line "vram in use" "${used:-?} MiB"
else
    line "gpu" "nvidia-smi not found"
fi

if [ -r /proc/cpuinfo ]; then
    line "cpu" "$(awk -F': ' '/model name/{print $2; exit}' /proc/cpuinfo)"
    line "threads" "$(grep -c ^processor /proc/cpuinfo)"
fi
line "ram" "$(awk '/MemTotal/{printf "%.0f GiB\n", $2/1048576}' /proc/meminfo 2>/dev/null)"
line "os" "$(awk -F= '/^PRETTY_NAME/{gsub(/"/,"",$2); print $2}' /etc/os-release 2>/dev/null)"
line "kernel" "$(uname -r)"

# ---- the engines, each in whichever way it will say
engine_version() {   # engine_version <label> <url> <path> [jq-key]
    local label="$1" url="$2" path="$3" key="${4:-version}"
    local body
    body=$(curl -s --max-time 4 "$url$path" 2>/dev/null)
    if [ -z "$body" ]; then
        line "$label" "not answering at $url"
        return
    fi
    local value
    value=$(printf '%s' "$body" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if isinstance(d, dict):
    for k in ('$key', 'version', 'build_info'):
        v = d.get(k)
        if isinstance(v, str) and v:
            print(v); break
" 2>/dev/null)
    line "$label" "${value:-running, version not declared}"
}

engine_version "tabbyapi" "http://127.0.0.1:8091" "/health"
engine_version "llama.cpp" "http://127.0.0.1:8090" "/props"
engine_version "lmstudio" "http://127.0.0.1:1234" "/v1/models"
engine_version "ollama" "http://127.0.0.1:11434" "/api/version"

# ---- the engines that keep their version on disk, since they will not say
if have git; then
    for d in "$HOME/tools/tabbyAPI:tabbyapi source" "$HOME/tools/llama.cpp:llama.cpp source"; do
        path="${d%%:*}"; label="${d##*:}"
        [ -d "$path/.git" ] || continue
        rev=$(git -C "$path" log -1 --format='%h %ad' --date=short 2>/dev/null)
        [ -n "$rev" ] && line "$label" "$rev"
    done
fi
if [ -x "$HOME/tools/tabbyAPI/venv/bin/python" ]; then
    ver=$("$HOME/tools/tabbyAPI/venv/bin/python" -c \
        "import importlib.metadata as m; print(m.version('exllamav3'))" 2>/dev/null)
    [ -n "$ver" ] && line "exllamav3" "$ver"
fi
