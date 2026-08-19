"""Renderer contract: corpus-evidence feature set, per-block source-line
anchors, code-heavy inline safety (snake_case never italicizes), and the
nearest-anchor mapping."""

from cjm_session_scratchpad_qt.render import nearest_anchor, render_html

TOKENS = {"raised": "#eeeeee", "border": "#bbbbbb", "font-mono-size": 11.0}


def render(text):
    return render_html(text, TOKENS, "TestMono")


def test_heading_levels_carry_anchors():
    r = render("# One\n\n### Three")
    assert '<h1><a name="L0"></a>One</h1>' in r.html
    assert '<h3><a name="L2"></a>Three</h3>' in r.html
    assert r.anchor_lines == [0, 2]


def test_paragraph_preserves_line_breaks():
    r = render("first line\nsecond line")
    assert "first line<br/>second line" in r.html


def test_inline_trio_and_links():
    r = render("**bold** and *ital* and `code` and [t](https://x.dev)")
    assert "<b>bold</b>" in r.html
    assert "<i>ital</i>" in r.html
    assert ">code</code>" in r.html and "TestMono" in r.html
    assert '<a href="https://x.dev">t</a>' in r.html


def test_snake_case_survives_dunder_bolds():
    r = render("call load_tui_state then a_b_c")
    assert "<i>" not in r.html and "<b>" not in r.html
    r2 = render("__init__ runs first")  # CommonMark/Typora both bold this
    assert "<b>init</b>" in r2.html


def test_formatting_inside_code_span_is_literal():
    r = render("`**not bold**` outside")
    assert "<b>" not in r.html
    assert "**not bold**" in r.html


def test_fenced_code_block_escapes_and_anchors():
    r = render("```python\nx = 1 < 2  # **raw**\n```")
    assert "<pre" in r.html and "x = 1 &lt; 2" in r.html
    assert "<b>" not in r.html
    assert r.anchor_lines == [0]


def test_unclosed_fence_runs_to_end():
    r = render("```\nleft open\nstill code")
    assert "still code" in r.html and r.html.count("<pre") == 1


def test_nested_lists_anchor_each_item():
    r = render("- a\n- b\n  - b1\n- c")
    assert r.html.count("<li>") == 4
    assert r.html.count("<ul>") == 2
    assert r.anchor_lines == [0, 1, 2, 3]


def test_ordered_list():
    r = render("1. one\n2. two")
    assert "<ol>" in r.html and r.html.count("<li>") == 2


def test_blank_line_between_items_continues_list():
    r = render("- a\n\n- b")
    assert r.html.count("<ul>") == 1 and r.html.count("<li>") == 2


def test_blockquote_single_anchor():
    r = render("> quoted **bold**\n> more")
    assert "<blockquote>" in r.html
    assert "<b>bold</b>" in r.html
    assert r.anchor_lines == [0]


def test_table_renders_header_bold():
    r = render("| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<table" in r.html
    assert "<td><b>a</b></td>" in r.html
    assert "<td>1</td>" in r.html


def test_hr_emits_no_anchor():
    r = render("before\n\n---\n\nafter")
    assert "<hr/>" in r.html
    assert 2 not in r.anchor_lines  # nothing for scrollToAnchor to miss


def test_nearest_anchor_maps_greatest_at_or_below():
    lines = [0, 4, 9, 20]
    assert nearest_anchor(lines, 0) == 0
    assert nearest_anchor(lines, 8) == 4
    assert nearest_anchor(lines, 9) == 9
    assert nearest_anchor(lines, 99) == 20
    assert nearest_anchor([], 5) is None


def test_empty_document():
    r = render("")
    assert r.html == "" and r.anchor_lines == []
