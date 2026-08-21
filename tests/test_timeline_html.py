"""Timeline HTML assembly: lanes, affordance links, chips, raw mode, linkify."""

from cjm_session_scratchpad_qt.timeline import TimelineEntry
from cjm_session_scratchpad_qt.timeline_html import (
    build_timeline_html, lane_filter, linkify_ids)

THEME = {"content-dim": "#888", "accent": "#36c", "note": "#749",
         "ok": "#2a4", "font-mono-size": 11.0}


def entry(uuid, source="cc-transcript", role="user", text="hello", ts="2026-08-21T10:00:00.000Z",
          active=True, sent=False):
    return TimelineEntry(node_id=f"node-{uuid}", source_uuid=uuid, role=role,
                         source=source, text=text, timestamp=ts,
                         editable=(source == "composer"), on_active_path=active,
                         sent=sent)


def test_cards_carry_identity_and_copy_affordance():
    html = build_timeline_html([entry("u1")], THEME, "monospace")
    assert 'copy://node-u1' in html          # copy-id link
    assert 'name="m-u1"' in html             # jump anchor
    assert "YOU" in html


def test_part_cards_carry_select_and_edit_links():
    html = build_timeline_html([entry("c1", source="composer")], THEME, "monospace")
    assert 'sel://c1' in html and 'edit://c1' in html
    assert "PART" in html


def test_sent_marker_and_selection_checkbox():
    html = build_timeline_html([entry("c1", source="composer", sent=True)],
                               THEME, "monospace", selected=["c1"])
    assert "✓ sent" in html and "☑" in html


def test_superseded_run_collapses_behind_chip():
    entries = [entry("u1"),
               entry("a1", role="assistant", ts="2026-08-21T10:01:00.000Z", active=False),
               entry("u2", ts="2026-08-21T10:02:00.000Z")]
    html = build_timeline_html(entries, THEME, "monospace")
    assert "1 superseded message(s)" in html
    assert "m-a1" not in html                # folded away until expanded
    html2 = build_timeline_html(entries, THEME, "monospace", expanded={1})
    assert "m-a1" in html2 and "collapse" in html2


def test_raw_mode_escapes_markdown_source():
    html = build_timeline_html([entry("u1", text="**bold** <tag>")], THEME,
                               "monospace", raw=True)
    assert "**bold**" in html and "&lt;tag&gt;" in html
    assert "<b>bold</b>" not in html


def test_lane_filters():
    entries = [entry("u1"), entry("c1", source="composer")]
    assert [e.source_uuid for e in lane_filter(entries, "composition")] == ["c1"]
    assert [e.source_uuid for e in lane_filter(entries, "transcript")] == ["u1"]
    assert len(lane_filter(entries, "all")) == 2


def test_linkify_wraps_known_full_ids_only():
    html = linkify_ids("see 0123456789abcdef0123 and deadbeef", ["0123456789abcdef0123"])
    assert '<a href="jump://0123456789abcdef0123">' in html
    assert 'jump://deadbeef' not in html
