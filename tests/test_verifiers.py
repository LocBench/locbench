"""The two gates that decide whether something ships, verified.

`verify_piece.py` decides whether a piece can be published and
`verify_post.py` whether post texts fit the platform limits. A gate that gets
it wrong is worse than no gate: if it says "ok" to an over-length text, or "ok"
to a citation pointing at the wrong line, it publishes the error in your place.
"""
import importlib
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))

vp = importlib.import_module("verify_piece")
vpost = importlib.import_module("verify_post")


# ---------------------------------------------------------- verify_post

def test_text_over_the_limit_is_an_error(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("<!-- limit: 10 -- fake -->\n\n```\nthis line is far too long\n```\n",
                 encoding="utf-8")
    ok, err = vpost.check(f)
    assert (ok, err) == (0, 1)


def test_text_within_the_limit_is_not_an_error(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("<!-- limit: 100 -- fake -->\n\n```\nshort\n```\n", encoding="utf-8")
    ok, err = vpost.check(f)
    assert (ok, err) == (1, 0)


def test_a_marker_without_a_block_is_an_error(tmp_path):
    """A marker that checks nothing is worse than no marker."""
    f = tmp_path / "p.md"
    f.write_text("<!-- limit: 10 -- fake -->\n\nno block here\n", encoding="utf-8")
    ok, err = vpost.check(f)
    assert err == 1


def test_a_url_counts_as_23_characters_on_x():
    """X shortens every link to 23 characters: without this, a post with a link
    looks longer than X counts it, and gets truncated for nothing."""
    url = "https://example.invalid/" + "a" * 200
    assert vpost.count(url, per_x=True) == 23
    assert vpost.count(url, per_x=False) == len(url)


def test_the_markers_in_the_real_post_file_are_found():
    """The tests above write the marker as a literal, so they cannot catch the
    marker convention drifting away from the real files.

    This one did happen: a rename touched the word inside the regular expression
    and the word inside the test string together, so both stayed consistent with
    each other while every real `<!-- limit: ... -->` in pieces/ stopped
    matching. Twenty-six tests passed and the tool found zero texts.

    So this test reads the actual file, not a convenient string.
    """
    real = Path(__file__).resolve().parent.parent / "pieces" / "01-post.md"
    assert real.exists(), f"missing {real}"
    found = vpost.blocks_with_limit(real.read_text(encoding="utf-8"))
    assert len(found) == 4, f"expected 4 marked texts, found {len(found)}"


def test_the_x_limit_is_recognised_by_its_threshold(tmp_path):
    """Below 280 the count is X's, with links shortened."""
    f = tmp_path / "p.md"
    body = "https://example.invalid/" + "a" * 300
    f.write_text(f"<!-- limit: 280 -- un post -->\n\n```\n{body}\n```\n", encoding="utf-8")
    ok, err = vpost.check(f)
    assert (ok, err) == (1, 0), "a long URL must not push an X post over the limit"


# --------------------------------------------------------- verify_piece

def _fake_sources(tmp_path, monkeypatch):
    root = tmp_path / "src"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "file.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
    monkeypatch.setattr(vp, "SOURCE_ROOTS", [root])
    vp._CACHE_RIGHE = None          # the global cache must be reset between tests
    return root


def test_citations_are_extracted_with_line_numbers():
    text = "see `sub/file.py`, lines 1–2 and also `other.md` with no lines"
    found = {(m.group(1), m.group(2), m.group(3)) for m in vp.RE_CITATION.finditer(text)}
    assert ("sub/file.py", "1", "2") in found
    assert ("other.md", None, None) in found


def test_a_citation_to_a_missing_file_is_an_error(tmp_path, monkeypatch):
    _fake_sources(tmp_path, monkeypatch)
    e = vp.Report()
    vp.check_citations("see `sub/missing.py`, lines 1-2", e)
    assert any("not found" in x for x in e.errors)


def test_a_line_past_end_of_file_is_an_error(tmp_path, monkeypatch):
    _fake_sources(tmp_path, monkeypatch)
    e = vp.Report()
    vp.check_citations("see `sub/file.py`, lines 1-99", e)
    assert any("the file has" in x for x in e.errors)


def test_a_citation_to_empty_lines_is_an_error(tmp_path, monkeypatch):
    """The worst case is not the line that does not exist: it is the line that
    exists and is empty, because the check would pass without checking anything."""
    root = tmp_path / "src"
    root.mkdir()
    (root / "empty.py").write_text("x = 1\n\n\n\ny = 2\n", encoding="utf-8")
    monkeypatch.setattr(vp, "SOURCE_ROOTS", [root])
    vp._CACHE_RIGHE = None
    e = vp.Report()
    vp.check_citations("see `empty.py`, lines 2-4", e)
    assert any("are empty" in x for x in e.errors)


def test_an_unchecked_plan_item_is_not_checked(tmp_path, monkeypatch):
    """An unchecked item in a plan names work that does not exist yet.

    Checking it would be a false alarm, and a gate that cries wolf on every plan
    teaches people to stop reading it. A checked item, on the other hand, claims
    the file is there and must be checked.
    """
    _fake_sources(tmp_path, monkeypatch)
    e = vp.Report()
    vp.check_citations("- [ ] **`sub/planned.py`** — not written yet", e)
    assert e.errors == []
    assert e.checks == 0

    e = vp.Report()
    vp.check_citations("- [x] **done** — see `sub/planned.py`", e)
    assert any("not found" in x for x in e.errors)


def test_a_correct_citation_produces_no_errors(tmp_path, monkeypatch):
    _fake_sources(tmp_path, monkeypatch)
    e = vp.Report()
    vp.check_citations("see `sub/file.py`, lines 1-3", e)
    assert e.errors == []
    assert e.checks == 1


# ------------------------------------------------- a quote under a citation

def _fake_source_con_codice(tmp_path, monkeypatch):
    root = tmp_path / "src"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "file.py").write_text(
        'prompt_tokens = result.get("prompt_tokens")\n'
        'prompt_time = round(result.get("time_prefill"), 2)\n'
        'prompt_ts = (\n'
        '    "Indeterminate"\n'
        '    if prompt_time == 0\n'
        '    else round((prompt_tokens - cached_tokens) / prompt_time, 2)\n'
        ')\n', encoding="utf-8")
    monkeypatch.setattr(vp, "SOURCE_ROOTS", [root])
    vp._CACHE_RIGHE = None
    return root


def test_a_paraphrased_quote_under_a_citation_is_caught(tmp_path, monkeypatch):
    """The one that got out. A post quoted TabbyAPI's `prompt_ts` as two clean
    lines with the zero guard and the rounding removed, under the line number of
    the real thing. The audience for that post opens the source, and the source
    disagrees."""
    _fake_source_con_codice(tmp_path, monkeypatch)
    e = vp.Report()
    vp.check_quotes(
        "see `sub/file.py:2`:\n\n"
        '    prompt_time = round(result.get("time_prefill"), 2)\n'
        '    prompt_ts   = (prompt_tokens - cached_tokens) / prompt_time\n',
        e)
    assert any("not in that file" in w for w in e.warnings), e.warnings


def test_an_exact_quote_under_a_citation_is_not_flagged(tmp_path, monkeypatch):
    _fake_source_con_codice(tmp_path, monkeypatch)
    e = vp.Report()
    vp.check_quotes(
        "see `sub/file.py:2`:\n\n"
        '    prompt_time = round(result.get("time_prefill"), 2)\n'
        '    else round((prompt_tokens - cached_tokens) / prompt_time, 2)\n',
        e)
    assert e.warnings == []
    assert e.checks >= 2


def test_prose_under_a_citation_is_not_read_as_code(tmp_path, monkeypatch):
    """The whole body of a post is one fenced block, because a post is meant to
    be pasted. Reading every long line in it as a quotation turns each sentence
    into a violation, and a gate that cries wolf is a gate nobody reads by the
    time it matters."""
    _fake_source_con_codice(tmp_path, monkeypatch)
    e = vp.Report()
    vp.check_quotes(
        "see `sub/file.py:2`:\n\n"
        "    Careful numerator: uncached tokens. The window comes from elsewhere\n"
        "    and it is documented as the time up to the first token produced.\n",
        e)
    assert e.warnings == []
    assert e.checks == 0


def test_a_block_far_from_the_citation_is_not_attributed_to_it(tmp_path, monkeypatch):
    """The window is bounded on purpose. Searching to the end of the document
    let a citation reach a block four sections later and call it a misquote."""
    _fake_source_con_codice(tmp_path, monkeypatch)
    e = vp.Report()
    vp.check_quotes(
        "see `sub/file.py:2`.\n\n"
        + "More prose here, several paragraphs of it, going on for a while.\n" * 6
        + '\n    prompt_ts   = (prompt_tokens - cached_tokens) / prompt_time\n',
        e)
    assert e.checks == 0, "a distant block was attributed to the citation"
