#!/usr/bin/env bash
# fetch-sources.sh — the engine source the numbers were measured on.
#
# The repository does not vendor llama.cpp, TabbyAPI or exllamav3. A citation
# into them is therefore unverifiable on a fresh clone, which is the wrong thing
# for a project whose claim is that a reader can check it. This script downloads
# the exact files, at the exact versions, into .sources/ (gitignored). The gate
# looks there first.
#
#   bin/fetch-sources.sh
#   python3 bin/verify_piece.py --all
#
# Network is required once. Nothing outside .sources/ is touched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${LOCBENCH_SOURCES_DEST:-$ROOT/.sources}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The versions are the ones in data/2026-10-03-environment.txt. They are pinned
# here rather than taken from whatever happens to be installed on the machine.
LLAMA_COMMIT="c85b92c"
TABBY_COMMIT="be74bf0"
EXLLAMA_VERSION="1.5.2"
EXLLAMA_WHEEL="https://files.pythonhosted.org/packages/04/35/52c1d44998ebdeab4424b4cd68b2d73ab0e0a1f2d84e61d31ad1abb01545/exllamav3-1.5.2-py3-none-any.whl"

fetch() {
    local url="$1" out="$2"
    mkdir -p "$(dirname "$out")"
    curl -fsSL --retry 3 --retry-delay 2 "$url" -o "$out"
    test -s "$out" || { echo "empty download: $url" >&2; exit 1; }
    echo "  $(du -h "$out" | cut -f1)  ${out#"$ROOT"/}"
}

echo "LocBench sources"
echo "  llama.cpp   $LLAMA_COMMIT"
echo "  TabbyAPI    $TABBY_COMMIT"
echo "  exllamav3   $EXLLAMA_VERSION"
echo

fetch "https://raw.githubusercontent.com/ggml-org/llama.cpp/$LLAMA_COMMIT/tools/server/server-context.cpp" \
      "$DEST/tools/server/server-context.cpp"
fetch "https://raw.githubusercontent.com/ggml-org/llama.cpp/$LLAMA_COMMIT/tools/server/server-common.h" \
      "$DEST/tools/server/server-common.h"
fetch "https://raw.githubusercontent.com/theroyallab/tabbyAPI/$TABBY_COMMIT/backends/exllamav3/model.py" \
      "$DEST/backends/exllamav3/model.py"
fetch "$EXLLAMA_WHEEL" "$TMP/exllamav3-$EXLLAMA_VERSION.whl"

python3 - "$TMP/exllamav3-$EXLLAMA_VERSION.whl" "$DEST" <<'PY'
import sys
import zipfile
from pathlib import Path

wheel, dest = Path(sys.argv[1]), Path(sys.argv[2])
with zipfile.ZipFile(wheel) as z:
    for name in ("exllamav3/generator/generator.py", "exllamav3/generator/job.py"):
        out = dest / "generator" / Path(name).name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(z.read(name))
        print(f"  {out.stat().st_size / 1024:6.0f}K  {out.relative_to(dest)}")
PY

# A download that is a 404 page is not a source. Check for something only the
# real file has, so this script fails here rather than in the gate.
check() {
    local file="$1" needle="$2"
    grep -q -- "$needle" "$file" || {
        echo "unexpected content in $file (missing: $needle)" >&2
        exit 1
    }
}
check "$DEST/tools/server/server-context.cpp" "update_prompt_start"
check "$DEST/tools/server/server-common.h" "n_prompt_tps"
check "$DEST/backends/exllamav3/model.py" "prompt_ts"
check "$DEST/generator/generator.py" "time_prefill"
check "$DEST/generator/job.py" "self.time_prefill"

cat > "$DEST/SOURCES.txt" <<EOF
LocBench — sources used by the citations
llama.cpp   $LLAMA_COMMIT   2026-09-29
TabbyAPI    $TABBY_COMMIT   2026-09-28
exllamav3   $EXLLAMA_VERSION
downloaded  $(date -u +%Y-%m-%dT%H:%M:%SZ)

The gate (bin/verify_piece.py) looks in .sources/ before any other root.
EOF

echo
echo "Okay. The gate will now check citations against $DEST"
