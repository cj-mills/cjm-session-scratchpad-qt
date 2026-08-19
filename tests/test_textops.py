"""Wrap-selection operators: wrap, both unwrap directions, caret-only."""

from cjm_session_scratchpad_qt.textops import wrap_selection

DOC = "make it bold today"


def test_wrap_selection_adds_markers():
    r = wrap_selection(DOC, 8, 12, "**")
    assert r.text == "**bold**"
    assert (r.start, r.end) == (8, 12)
    assert r.cursor == 16 and r.anchor == 8


def test_unwrap_when_selection_includes_markers():
    doc = "make it **bold** today"
    r = wrap_selection(doc, 8, 16, "**")
    assert r.text == "bold"
    assert r.cursor == 12 and r.anchor == 8


def test_unwrap_when_markers_surround_selection():
    doc = "make it **bold** today"
    r = wrap_selection(doc, 10, 14, "**")
    assert r.text == "bold"
    assert (r.start, r.end) == (8, 16)


def test_caret_only_inserts_empty_pair_cursor_inside():
    r = wrap_selection(DOC, 5, 5, "`")
    assert r.text == "``"
    assert r.cursor == 6 and r.anchor == 6


def test_single_char_markers():
    r = wrap_selection(DOC, 8, 12, "*")
    assert r.text == "*bold*"
