"""The README promises one language, and the promise is checkable.

It says, in a block quote near the end:

    Everything here is in English: this file, the protocol, the pieces, the
    commit messages, the file and directory names, the analysis output and the
    CSV column names. Nothing is left in another language for a reader to
    stumble into.

Eleven file names broke it -- `curva`, `ordine`, `prosa`, `otto` -- and they
broke it for a month without anything noticing, because nothing was looking. An
external audit found them; a repository whose whole claim is that a reader can
check its work should not need an auditor for this.

**A word list is not a language detector, and it is worth being precise about
what that costs.** It cannot tell Italian from Portuguese, it will not catch a
word nobody thought to write down, and every word in it got there because
somebody remembered it. What it can do is catch the class of mistake that
actually happened: a measurement run named in the language of whoever ran it,
inside a repository written in another one. That is a small guarantee, honestly
stated, and it is more than the previous arrangement offered, which was none.

Only file and directory names are checked, and that is deliberate. A name is a
decision somebody made and can be asked to make differently. A data value is
not: `data/2026-09-usage.jsonl` records `batteria/1.0` and `prova-effort/low` in
its `client` field because that is what the throwaway scripts called themselves
when they sent the requests, and the protocol declares them as such rather than
laundering them into English. Renaming a recorded value would be editing the
measurement to protect the prose.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Words that are Italian and are not also English, chosen so that a false
# positive is very unlikely: no music terms, no names, nothing that a technical
# repository might reach for in another sense. "otto" is in here because it is
# the one that got through.
ITALIAN = {
    "batteria", "cartella", "curva", "curve_it", "dati", "errore", "errori",
    "finale", "grafico", "grafici", "ieri", "iniziale", "lento", "misura",
    "misure", "nome", "nomi", "oggi", "ordine", "ordini", "otto", "penultimo",
    "prosa", "prova", "prove", "risultato", "risultati", "salute", "settimana",
    "tabella", "tabelle", "ultimo", "valori", "veloce",
}

# Nothing is exempt today. The set exists so that an exemption has to be written
# down, with a reason, rather than arranged by not testing that path.
EXEMPT = set()


def tracked_names():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def words_in(name):
    """The tokens a name is built from, so `curve-tabbyapi.jsonl` is three."""
    return [w for w in re.split(r"[/_.\-]+", name.lower()) if w]


def test_no_tracked_file_or_directory_is_named_in_another_language():
    offenders = []
    for name in tracked_names():
        if name in EXEMPT:
            continue
        for word in words_in(name):
            if word in ITALIAN:
                offenders.append((name, word))
    assert not offenders, (
        "the README promises English names and these are not: %s"
        % ", ".join("%s (%s)" % (n, w) for n, w in offenders))


def test_the_check_can_actually_fail():
    """A guard that has never been seen to fail is a guard nobody should trust.

    The three names below are the ones this file was written for. If the split
    or the comparison were wrong, the test above would pass on a repository full
    of Italian and look exactly as green as it does now.
    """
    assert words_in("data/2026-10-03-curva-tabbyapi.jsonl") == [
        "data", "2026", "10", "03", "curva", "tabbyapi", "jsonl"]
    assert words_in("2026-10-03-ordine-vocab-1.jsonl").count("ordine") == 1
    assert "otto" in words_in("data/2026-10-03-otto-stream-ollama.jsonl")

    for name in ("data/2026-10-03-curva-tabbyapi.jsonl",
                 "data/2026-10-03-ordine-vocab-1.jsonl",
                 "data/2026-10-03-otto-stream-ollama.jsonl",
                 "2026-10-03-prosa-corpus.jsonl"):
        assert any(w in ITALIAN for w in words_in(name)), \
            "the list does not contain a word from %s" % name
