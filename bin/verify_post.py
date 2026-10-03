#!/usr/bin/env python3
"""Checks that publish-ready texts fit the platform limits.

X truncates at 280 characters **silently**: the text goes out cut in half and
you do not notice until someone points it out. Reddit rejects over-long titles.
GitHub truncates the repository description. All of them are errors you only see
afterwards, in front of everyone.

Reads the markers `<!-- limit: N -- what for -->` and checks the code block
that follows them.

    python3 bin/verify_post.py pieces/01-post.md
    python3 bin/verify_post.py --all

Exits with code 1 if anything overflows.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# X shortens every URL to 23 characters whatever its real length (t.co).
# Without this, a post with a link looks longer than X counts it.
LUNGHEZZA_URL_X = 23
RE_URL = re.compile(r"https?://\S+")

RE_MARCATORE = re.compile(r"<!--\s*limit:\s*(\d+)\s*(?:--\s*(.*?))?\s*-->")


def blocks_with_limit(text):
    """(limit, description, text) for each marker, with the block that follows."""
    rows = text.splitlines()
    out = []
    i = 0
    while i < len(rows):
        m = RE_MARCATORE.search(rows[i])
        if not m:
            i += 1
            continue
        limit = int(m.group(1))
        description = (m.group(2) or "").strip()
        # the first fenced block after the marker
        j = i + 1
        while j < len(rows) and not rows[j].startswith("```"):
            j += 1
        if j >= len(rows):
            out.append((limit, description, None, i + 1))
            break
        k = j + 1
        body = []
        while k < len(rows) and not rows[k].startswith("```"):
            body.append(rows[k])
            k += 1
        out.append((limit, description, "\n".join(body).strip(), i + 1))
        i = k + 1
    return out


def count(text, per_x):
    """Characters as the platform counts them."""
    if per_x:
        # X counts a URL as 23 characters, always
        return len(RE_URL.sub("x" * LUNGHEZZA_URL_X, text))
    return len(text)


def check(path):
    text = Path(path).read_text(encoding="utf-8")
    blocks = blocks_with_limit(text)
    if not blocks:
        print(f"  (no `limit:` marker in {path})")
        return 0, 0

    errors = ok = 0
    print(f"\n=== {path} ===")
    for limit, description, body, line in blocks:
        if body is None:
            print(f"  ERROR    line {line}: marker with no code block after it")
            errors += 1
            continue
        per_x = limit <= 280
        n = count(body, per_x)
        label = description or "no description"
        state = "ok " if n <= limit else "OVER"
        print(f"  {state}  {n:>4}/{limit}  {label}")
        if n > limit:
            errors += 1
            print(f"         {n - limit} characters too long (line {line})")
        else:
            ok += 1
        if per_x and RE_URL.search(body):
            print("         note: contains a URL, counted as 23 characters")
    return ok, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("post", nargs="?", help="the file holding the texts")
    ap.add_argument("--all", action="store_true", help="check every *-post.md")
    args = ap.parse_args()

    if args.all:
        files = sorted((ROOT / "pieces").glob("*-post.md"))
    elif args.post:
        files = [Path(args.post)]
    else:
        ap.error("give a file, or --all")

    tot_ok = tot_err = 0
    for f in files:
        if not f.exists():
            print(f"  ERROR    no such file: {f}")
            tot_err += 1
            continue
        ok, err = check(f)
        tot_ok += ok
        tot_err += err

    print(f"\n{tot_ok} texts within limits, {tot_err} over")
    return 1 if tot_err else 0


if __name__ == "__main__":
    sys.exit(main())
