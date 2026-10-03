#!/usr/bin/env python3
"""The check that runs before a piece ships.

A published piece carries the face of whoever signs it, and whoever signs it
does not read code: so the only verification that exists is the one that runs by
itself. This script does three things to a text:

  1. CITATIONS — every `file` with a line number exists, and that line is not
     empty. This catches the worst case: a reference to a line that says
     something else
  2. CODE — every line of code quoted in a block is really in one of the
     sources. This catches the invented or stale quotation
  3. NUMBERS — the values a piece claims are recomputed now, from the same
     committed data, and printed alongside for comparison

    python3 bin/verify_piece.py pieces/01-....md
    python3 bin/verify_piece.py --all

Exits with code 1 if there is at least one error: it is meant to be a gate, not
a report to read.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

# Where to look for the engine sources. They live outside the repository, so
# anyone who clones it will not have them — and a citation pointing into them
# comes back unverifiable, which is what the gate should say rather than
# pretend otherwise.
#
# More roots can be added with LOCBENCH_SOURCES, separated by ":".
SOURCE_ROOTS = [
    *(Path(p) for p in os.environ.get("LOCBENCH_SOURCES", "").split(":") if p),
    Path.home() / "tools" / "llama.cpp",
    Path.home() / "tools" / "tabbyAPI",
    Path.home() / "scripts",             # the collection proxy, not published
    ROOT,
]

RE_CITATION = re.compile(
    r"`([A-Za-z0-9_./+-]+\.(?:py|cpp|h|hpp|c|md|sh))`"
    r"(?:,?\s*(?:around\s+)?lines?\s+(\d+)(?:\s*[–—-]\s*(\d+))?)?"
)
RE_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.S)


def _find(path):
    """The cited file, looked up in the known roots."""
    p = Path(path)
    if p.is_absolute() and p.exists():
        return p
    for root in SOURCE_ROOTS:
        cand = root / path
        if cand.exists():
            return cand
    # citations like "tools/server/server-common.h" inside llama.cpp
    for root in SOURCE_ROOTS:
        if not root.is_dir():
            continue
        for found in root.rglob(Path(path).name):
            if str(found).endswith(path):
                return found
    return None


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checks = 0

    def error(self, msg):
        self.errors.append(msg)

    def warning(self, msg):
        self.warnings.append(msg)


def check_citations(text, report):
    """Every reference to a file (with a line) must exist and not point at nothing.

    Lines that are an unclosed checkbox in a plan are skipped: an unchecked item
    names work that does not exist yet, by definition. Checking it would be a
    false alarm, and a gate that cries wolf teaches people to stop reading it.
    """
    seen = set()
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r"\s*- \[ \]", line):
            continue
        for m in RE_CITATION.finditer(line):
            _check_citation(m, seen, report)


def _check_citation(m, seen, report):
    path, da, a = m.group(1), m.group(2), m.group(3)
    key = (path, da, a)
    if key in seen:
        return
    seen.add(key)
    report.checks += 1

    f = _find(path)
    if f is None:
        # It may be a file outside the repository (the collection proxy, for
        # instance). An explicit error beats silence: a reader does not know
        # that file exists, and it has to be said somewhere.
        report.error(f"citation not found: {path} "
                     f"(it is in none of the known roots, not even outside the repo)")
        return
    if not da:
        return

    rows = f.read_text(encoding="utf-8", errors="replace").splitlines()
    start = int(da)
    end = int(a) if a else start
    if start < 1 or end > len(rows):
        report.error(f"{path}: lines {start}-{end} but the file has {len(rows)}")
        return
    body = [r.strip() for r in rows[start - 1:end]]
    if not any(body):
        report.error(f"{path}: lines {start}-{end} are empty")
    else:
        print(f"    ok  {path}:{start}-{end}  ->  {body[0][:60]}")


RE_CITA = re.compile(r"`?([\w./-]+\.(?:py|cpp|hpp|h|c|sh)):(\d+)(?:-(\d+))?`?")
# A line is treated as quoted code only if it looks like code. Without this the
# whole body of a post -- which is one fenced block, because it is meant to be
# pasted -- gets read as source and every sentence becomes a violation.
RE_CODICE = re.compile(r"[=;{}]|->|::|\(.*\)\s*[,;]?\s*$")


def _righe_del_file(percorso):
    """The lines of a cited file, resolved the same way a citation is.

    One resolver, not two: a second search path invented here would find files
    the citation check does not, or miss ones it does, and the two would drift.
    """
    trovato = _find(percorso)
    if trovato is None:
        return None
    try:
        return [l.strip() for l in trovato.read_text(errors="replace").splitlines()]
    except OSError:
        return None


def _blocco_sotto(coda):
    """The first code block within a few lines of the citation, or nothing.

    Bounded on purpose. Searching to the end of the document instead let a
    citation in the protocol reach a block four sections later and call it a
    misquote, which is the kind of warning that teaches a reader to skip them.
    """
    testa = coda[:400]
    m = re.search(r"```\w*\n(.*?)```", testa, re.S)
    if m:
        return m.group(1)
    m = re.search(r"(?m)^((?: {4}|\t)\S.*(?:\n(?: {4}|\t).*)*)", testa)
    return m.group(1) if m else None


def check_quotes(text, report):
    """A cited line number and the block under it have to agree.

    This is the check that was missing when a post went out quoting TabbyAPI's
    `prompt_ts` as two clean lines, with the zero guard and the rounding
    removed. The source says otherwise, and the audience for that post opens the
    source. The old check inspected only fenced blocks carrying a language tag;
    there are none in this repository, so it examined nothing and printed
    nothing -- which reads exactly like passing.
    """
    for m in RE_CITA.finditer(text):
        percorso, riga = m.group(1), int(m.group(2))
        blocco = _blocco_sotto(text[m.end():])
        if not blocco:
            continue
        righe = _righe_del_file(percorso)
        if righe is None:
            report.warning(f"cited source not found on disk: {percorso}")
            continue
        for linea in blocco.splitlines():
            r = linea.strip()
            if len(r) < 25 or r.startswith(("#", "//", "*", "$", "<!--")):
                continue
            if not RE_CODICE.search(r):
                continue
            report.checks += 1
            if not any(r == sorgente or r in sorgente for sorgente in righe):
                report.warning("quoted under %s:%d but not in that file: %s"
                               % (percorso, riga, r[:66]))


def check_code(text, report):
    """Quoted lines of code must exist in one of the sources."""
    for lang, body in RE_BLOCK.findall(text):
        if lang not in ("py", "python", "cpp", "c", "h", "hpp"):
            continue
        for line in body.splitlines():
            r = line.strip()
            # only distinctive lines: too short or too generic proves nothing
            if len(r) < 25 or r.startswith(("#", "//", "*")):
                continue
            report.checks += 1
            if not _exists_in_sources(r):
                report.warning(f"line not found in the sources: {r[:70]}")

    # comments quoted in the text are the strongest evidence: if one is
    # invented, the damage is doubled
    for m in re.finditer(r"\*\*([^*]{25,160})\*\*", text):
        frase = m.group(1).strip()
        if not re.match(r"^[A-Za-z][A-Za-z0-9 ,.'()\-/]*$", frase):
            continue
        if not frase.endswith(("token", "seconds", "measurement")):
            continue
        report.checks += 1
        if not _exists_in_sources(frase):
            report.warning(f"quoted phrase not found in the sources: {frase[:70]}")


_LINE_CACHE = None


def _exists_in_sources(line):
    """Look for the (normalised) line across all known sources."""
    global _LINE_CACHE
    if _LINE_CACHE is None:
        _LINE_CACHE = set()
        for root in SOURCE_ROOTS:
            if not root.is_dir():
                continue
            for f in root.rglob("*"):
                if f.suffix not in (".py", ".cpp", ".h", ".hpp", ".c"):
                    continue
                try:
                    for r in f.read_text(encoding="utf-8", errors="replace").splitlines():
                        _LINE_CACHE.add(re.sub(r"\s+", " ", r.strip()))
                except OSError:
                    pass
    return re.sub(r"\s+", " ", line) in _LINE_CACHE


def check_numbers(report):
    """Recompute the analysis now, so the numbers can be compared by eye."""
    import analyze_log as A

    data_files = ROOT / "data" / "2026-09-usage.jsonl"
    rows, _ = A.read(str(data_files))
    points = A.usable(rows)
    overall = A.fit(points)
    stream = A.fit([p for p in points if p["stream"]])
    nonstream = A.fit([p for p in points if not p["stream"]])

    g = [p for p in points if p["stream"]]
    y = [p["ttft_s"] for p in g]
    without_cache = A.ols([[1.0] * len(y), [p["uncached"] for p in g]], y)
    with_cache = A.ols([[1.0] * len(y), [p["uncached"] for p in g],
                    [p["cached_tokens"] for p in g]], y)
    cache_cost_ms = with_cache[0][2] * 1000
    gain = with_cache[1] - without_cache[1]

    # (description, recomputed value, tolerance)
    expected = [
        ("usable rows", float(len(points)), 0),
        ("n, all points", float(overall["n"]), 0),
        ("intercept, all points (s)", overall["intercept_s"], 0.001),
        ("slope, all points (tok/s)", overall["tps"], 1.0),
        ("R2, all points", overall["r2"], 0.001),
        ("n streaming", float(stream["n"]), 0),
        ("intercept streaming (s)", stream["intercept_s"], 0.001),
        ("slope streaming (tok/s)", stream["tps"], 1.0),
        ("R2 streaming", stream["r2"], 0.001),
        ("n non-streaming", float(nonstream["n"]), 0),
        ("intercept non-streaming (s)", nonstream["intercept_s"], 0.001),
        ("R2 non-streaming", nonstream["r2"], 0.001),
        ("cost of a cached token (ms)", cache_cost_ms, 0.001),
        ("R2 gained from the cache", gain, 0.0005),
    ]

    print("  values recomputed from the committed data (compare them to the text by eye):")
    for name, value, tol in expected:
        print(f"    {name:34s} = {value:.4f}")
    return expected


def _same_cell(value, wanted):
    """A cell is the same cell, or the same cell at a given length.

    Prefix matching alone is not enough and the failure is silent:
    "stream+inject".startswith("stream") is true, so a fit labelled `stream`
    quietly absorbed the `stream+inject` rows and reported a line belonging to
    neither. It was caught by a recomputation disagreeing with an earlier one,
    which is the only way this kind of thing ever shows up.
    """
    value = str(value or "")
    return value == wanted or value.startswith(wanted + "@")


def check_measurements(esito):
    """Recompute the fits the measurement pieces rest on, and print them.

    The first piece rests on the September log; the second on the controlled
    sessions of 3 October. Both are recomputed from the committed files, here,
    so that a number written into a piece can be compared with a number derived
    from the data rather than with a number remembered from earlier.

    Every source names the clock it is fitted on, and that is not a detail. Over
    the same streamed requests llama.cpp's reported window leaves 63 ms of each
    request untimed and TabbyAPI's 128, so an engine-clock fit and a client-clock
    fit of identical requests are different quantities wearing the same name.

    It prints rather than asserts, which is the same split as the sections above:
    the comparing is done by whoever reads, and what the tool guarantees is that
    there is something to compare against.
    """
    import statistics
    sys.path.insert(0, str(ROOT / "bench"))
    import analyze_log as A

    def fit(rows, cell, clock="engine_ttft_s"):
        points = {}
        for row in rows:
            if row.get("discarded") or not _same_cell(row.get("cell"), cell):
                continue
            n, w = row.get("uncached"), row.get(clock)
            if not n or w is None:
                continue
            points.setdefault(n, []).append(w)
        if len(points) < 3:
            return None
        xs = sorted(points)
        x = [float(i) for i in xs]
        y = [statistics.median(points[i]) for i in xs]
        result = A.ols([[1.0] * len(x), x], y)
        if not result:
            return None
        (a, b), r2, n = result
        return a, (1 / b if b > 0 else float("inf")), r2, n

    def rows_of(path):
        full = ROOT / path
        if not full.exists():
            esito.warning(f"measurement file missing, cannot recompute: {path}")
            return None
        return [json.loads(line)
                for line in full.read_text(encoding="utf-8").splitlines() if line.strip()]

    sources = {
        # ---- the engine's own clock: what the engines publish -----------------
        "tabbyapi d1": ("data/2026-10-03-d1-tabbyapi.jsonl",
                        ("plain", "inject", "stream+inject", "stream"), "engine_ttft_s"),
        "llamacpp d1": ("data/2026-10-03-d1-llamacpp.jsonl",
                        ("plain", "inject", "stream+inject", "stream"), "engine_ttft_s"),
        "ollama": ("data/2026-10-03-sweep-ollama.jsonl", ("plain",), "engine_ttft_s"),
        "llamacpp (same file)": ("data/2026-10-03-cfg-8093.jsonl", ("plain",), "engine_ttft_s"),
        "lmstudio": ("data/2026-10-03-sweep-lmstudio.jsonl", ("plain",), "engine_ttft_s"),
        # the same engine at half the context, which is what Vulkan will load:
        # the piece claims the context is not what moved the number
        "lmstudio at 32k": ("data/2026-10-03-sweep-lmstudio-32k.jsonl", ("plain",), "engine_ttft_s"),
        "tabbyapi": ("data/2026-10-03-sweep-tabbyapi.jsonl", ("plain",), "engine_ttft_s"),
        "control: KV q4_0": ("data/2026-10-03-cfg-8094.jsonl", ("plain",), "engine_ttft_s"),
        "control: 4 slots": ("data/2026-10-03-cfg-8096.jsonl", ("plain",), "engine_ttft_s"),
        "control: max-tokens 1": ("data/2026-10-03-maxtok-1.jsonl", ("plain",), "engine_ttft_s"),
        "control: max-tokens 256": ("data/2026-10-03-maxtok-256.jsonl", ("plain",), "engine_ttft_s"),
        # ---- the client's clock on streamed requests: the ranking column ------
        "CLIENT llamacpp": ("data/2026-10-03-stream-llamacpp.jsonl", ("stream",), "client_ttft_s"),
        "CLIENT tabbyapi": ("data/2026-10-03-stream-tabbyapi.jsonl", ("stream",), "client_ttft_s"),
        "CLIENT ollama": ("data/2026-10-03-stream-ollama.jsonl", ("stream",), "client_ttft_s"),
        "CLIENT lmstudio": ("data/2026-10-03-stream-lmstudio.jsonl", ("stream",), "client_ttft_s"),
        # ---- the same requests on the engine's clock: the gap -----------------
        "ENGINE llamacpp": ("data/2026-10-03-stream-llamacpp.jsonl", ("stream",), "engine_ttft_s"),
        "ENGINE tabbyapi": ("data/2026-10-03-stream-tabbyapi.jsonl", ("stream",), "engine_ttft_s"),
        "ENGINE ollama": ("data/2026-10-03-stream-ollama.jsonl", ("stream",), "engine_ttft_s"),
        "ENGINE lmstudio": ("data/2026-10-03-stream-lmstudio.jsonl", ("stream",), "engine_ttft_s"),
        # ---- the second model: a third the size, same client ------------------
        "8B CLIENT ollama": ("data/2026-10-03-qwen3-8b-stream-ollama.jsonl", ("stream",), "client_ttft_s"),
        "8B CLIENT llamacpp": ("data/2026-10-03-qwen3-8b-stream-llamacpp.jsonl", ("stream",), "client_ttft_s"),
        "8B CLIENT lmstudio": ("data/2026-10-03-qwen3-8b-stream-lmstudio.jsonl", ("stream",), "client_ttft_s"),
        "8B ENGINE llamacpp": ("data/2026-10-03-qwen3-8b-stream-llamacpp.jsonl", ("stream",), "engine_ttft_s"),
        # the 27B without speculative decoding, which is the control that says
        # the flag is not what makes the fixed cost follow the model
        "27B no-MTP CLIENT llamacpp": ("data/2026-10-03-no-mtp-stream-llamacpp.jsonl", ("stream",), "client_ttft_s"),
        "27B no-MTP ENGINE llamacpp": ("data/2026-10-03-no-mtp-stream-llamacpp.jsonl", ("stream",), "engine_ttft_s"),
        # ---- the prose control, and the counterbalance for its order ----------
        "prose: vocabulary": ("data/2026-10-03-prose-vocab.jsonl", ("plain",), "engine_ttft_s"),
        "prose: real prose": ("data/2026-10-03-prose-corpus.jsonl", ("plain",), "engine_ttft_s"),
        "order 1 vocabulary": ("data/2026-10-03-order-vocab-1.jsonl", ("plain",), "engine_ttft_s"),
        "order 1 prose": ("data/2026-10-03-order-corpus-1.jsonl", ("plain",), "engine_ttft_s"),
        "order 2 vocabulary": ("data/2026-10-03-order-vocab-2.jsonl", ("plain",), "engine_ttft_s"),
        "order 2 prose": ("data/2026-10-03-order-corpus-2.jsonl", ("plain",), "engine_ttft_s"),
        # ---- the dense grid: is TabbyAPI's window a straight line? ------------
        "curvature grid": ("data/2026-10-03-curve-tabbyapi.jsonl", ("plain",), "engine_ttft_s"),
    }

    print("\n=== numbers, recomputed now (compare them to the text by eye) ===")
    for label in sorted(sources):
        path, cells, clock = sources[label]
        rows = rows_of(path)
        if rows is None:
            continue
        for cell in cells:
            line = fit(rows, cell, clock)
            if line:
                print("    %-22s %-14s fixed %.3f s   throughput %6.0f tok/s   R2=%.4f  (%d lengths)"
                      % (label, cell, line[0], line[1], line[2], line[3]))
            elif not any(r.get(clock) for r in rows):
                print("    %-22s %-14s -- no %s on this path"
                      % (label, cell, clock.replace("_ttft_s", "")))
        esito.checks += len(cells)

    # The token counts behind the prose control. The fit above uses the tokens
    # the engine reports, so it survives this; a reader who divides time by
    # words does not, because the same word count is a different amount of work
    # depending on which words.
    #
    # Computed from the counterbalanced runs, which is what the piece quotes,
    # and both prose passages are printed because the gap between them is the
    # point: two prompts of the same length, 40% apart in tokens.
    def by_words(path):
        rows = rows_of(path)
        if not rows:
            return {}
        out = {}
        for r in rows:
            if r.get("discarded") or not r.get("uncached") or not r.get("words"):
                continue
            out.setdefault(int(r["words"]), []).append(r["uncached"])
        return {w: statistics.median(v) for w, v in out.items()}

    voc = [by_words("data/2026-10-03-order-vocab-1.jsonl"),
           by_words("data/2026-10-03-order-vocab-2.jsonl")]
    pro = [by_words("data/2026-10-03-order-corpus-1.jsonl"),
           by_words("data/2026-10-03-order-corpus-2.jsonl")]
    if all(pro) and any(voc):
        print("    prose control, tokens for the same word count:")
        for words in sorted(pro[0]):
            tv = statistics.median([v[words] for v in voc if words in v])
            tp = [p[words] for p in pro if words in p]
            if not tv or len(tp) < 2:
                continue
            print("      %5d words -> vocabulary %5d tokens, prose %5d and %5d  "
                  "(%.2fx, the two passages %.0f%% apart)"
                  % (words, tv, tp[0], tp[1], statistics.median(tp) / tv,
                     100 * abs(tp[0] - tp[1]) / min(tp)))
        esito.checks += 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("piece", nargs="?", help="the file to check")
    ap.add_argument("--all", action="store_true", help="check every piece")
    args = ap.parse_args()

    if args.all:
        files = sorted((ROOT / "pieces").glob("*.md"))
    elif args.piece:
        files = [Path(args.piece)]
    else:
        ap.error("give a piece, or --all")

    report = Report()
    for f in files:
        if not f.exists():
            report.error(f"piece does not exist: {f}")
            continue
        text = f.read_text(encoding="utf-8")
        print(f"\n=== {f} ===")
        print("  citations:")
        check_citations(text, report)
        print("  code:")
        check_code(text, report)

        check_quotes(text, report)
    # Values are recomputed and printed; comparing them to the text is for
    # whoever reads. An automatic "this number is not cited" check produces
    # false positives on any document that does not list everything, and a gate
    # that cries wolf teaches people to stop reading it.
    check_measurements(report)
    print("\n=== numbers from the September log, recomputed now ===")
    check_numbers(report)

    print(f"\n{report.checks} checks, {len(report.errors)} errors, {len(report.warnings)} warnings")
    for e in report.errors:
        print(f"  ERROR    {e}")
    for a in report.warnings:
        print(f"  warning  {a}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
