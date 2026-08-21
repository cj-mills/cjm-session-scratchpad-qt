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


# ---- v2 block gestures (DEC 671e9b11 pt 6) --------------------------------

from cjm_session_scratchpad_qt.textops import fence_selection, toggle_list


def test_fence_wraps_selected_lines_with_language():
    doc = "before\nprint(1)\nafter"
    start = doc.index("print")
    r = fence_selection(doc, start, start + len("print(1)"), "python")
    assert r.text == "```python\nprint(1)\n```"
    assert (r.start, r.end) == (start, start + len("print(1)"))


def test_fence_empty_selection_opens_block_caret_inside():
    doc = "line\n"
    r = fence_selection(doc, 5, 5, "bash")
    assert r.text == "```bash\n\n```"
    assert r.cursor == 5 + len("```bash\n")  # on the blank content line


def test_fence_toggles_off_an_existing_block():
    doc = "```python\nx = 1\n```"
    r = fence_selection(doc, 0, len(doc))
    assert r.text == "x = 1"


def test_unordered_list_applies_and_strips():
    doc = "alpha\nbeta"
    r = toggle_list(doc, 0, len(doc))
    assert r.text == "- alpha\n- beta"
    r2 = toggle_list(r.text, 0, len(r.text))
    assert r2.text == "alpha\nbeta"


def test_ordered_list_numbers_and_converts_unordered():
    doc = "- alpha\n- beta\n- gamma"
    r = toggle_list(doc, 0, len(doc), ordered=True)
    assert r.text == "1. alpha\n2. beta\n3. gamma"


def test_list_skips_blank_lines_and_keeps_indent():
    doc = "  alpha\n\n  beta"
    r = toggle_list(doc, 0, len(doc))
    assert r.text == "  - alpha\n\n  - beta"
