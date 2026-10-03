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
