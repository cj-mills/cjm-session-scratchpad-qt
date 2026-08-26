"""Timeline HTML assembly — the pure presentation half of the v2 reading view.

One QTextBrowser document renders the whole interleaved timeline (the v1
renderer, find-bar, selectable text, and anchor machinery ride along for
free); every gesture affordance is a LINK with a scheme the shell routes
(671e9b11 pt 4 — node-id affordances are load-bearing):

    copy://<node-id>     copy the node id
    edit://<uuid>        load a composer part into the composer (edit mode)
    sel://<uuid>         toggle a part's compose-send selection
    branch://<index>     expand/collapse a superseded transcript run
    jump://<uuid>        scroll to a message card (anchor m-<uuid>)

Bodies render through the owned markdown pipeline (raw mode swaps in escaped
<pre> — the source IS the stored text, DEC 671e9b11 pt 9), full node ids
appearing in any body linkify to jump:// when the target is on the timeline."""

import html as _html
import re
from datetime import datetime, tzinfo
from typing import Dict, List, Optional, Sequence, Set

from .render import render_html
from .timeline import timeline_blocks, TimelineEntry

ROLE_GLYPHS = {"user": "YOU", "assistant": "CLAUDE", "harness": "HARNESS"}

# Lanes: the interleaved default plus each chain alone (671e9b11 pt 1).
LANES = ("all", "composition", "transcript")


def _clock(ts: str, tz: Optional[tzinfo] = None) -> str:
    """HH:MM:SS of a stored UTC-Z stamp in LOCAL time ('' and odd shapes pass through).

    Display-only: sorting and identity stay on the raw ISO string (lexicographic
    — timeline.py's contract); tz overrides the machine zone for tests."""
    try:
        local = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(tz)
    except ValueError:
        return ts[11:19] if len(ts) >= 19 else ts
    return local.strftime("%H:%M:%S")


def _glyph(e: TimelineEntry) -> str:
    if e.source == "composer":
        return "PART"
    return ROLE_GLYPHS.get(e.role, e.role.upper() or "?")


def lane_filter(entries: Sequence[TimelineEntry], lane: str) -> List[TimelineEntry]:
    """The lane views: composition = composer-born, transcript = pulled."""
    if lane == "composition":
        return [e for e in entries if e.source == "composer"]
    if lane == "transcript":
        return [e for e in entries if e.source != "composer"]
    return list(entries)


def linkify_ids(body_html: str, uuids: Sequence[str]) -> str:
    """Wrap full node/source ids appearing as text in jump:// links —
    click-jump on node refs in rendered prose. Conservative: exact full
    tokens only, and never inside an existing tag/attribute."""
    for u in uuids:
        if not u or len(u) < 12:
            continue
        pattern = re.compile(r"(?<![\w/-])" + re.escape(u) + r"(?![\w-])")
        body_html = pattern.sub(
            lambda m: f'<a href="jump://{u}">{m.group(0)}</a>', body_html)
    return body_html


def card_html(e: TimelineEntry, theme: Dict, mono: str, *, raw: bool,
              selected: Sequence[str], editing: Optional[str],
              jump_uuids: Sequence[str]) -> str:
    """One message card: anchored header line (identity + affordances) +
    rendered or raw body."""
    dim = theme.get("content-dim", "#888888")
    accent = theme.get("accent", "#3d63a8")
    note = theme.get("note", "#7d4796")
    ok = theme.get("ok", "#2c7a41")
    warn = theme.get("warn", dim)
    color = (note if e.source == "composer"
             else warn if e.role == "harness"
             else accent if e.role == "user" else dim)
    short = e.node_id[:8]
    bits = [f'<b style="color:{color}">{_glyph(e)}</b>',
            _clock(e.timestamp),
            f'<span style="color:{dim}">{short}</span>',
            f'<a href="copy://{e.node_id}" style="color:{dim}">copy-id</a>']
    if e.editable:
        mark = "☑" if e.source_uuid in selected else "☐"
        bits.append(f'<a href="sel://{e.source_uuid}" style="color:{accent}">{mark} select</a>')
        label = "editing…" if editing == e.source_uuid else "edit"
        bits.append(f'<a href="edit://{e.source_uuid}" style="color:{accent}">{label}</a>')
        if e.sent:
            bits.append(f'<span style="color:{ok}">✓ sent</span>')
    if not e.on_active_path:
        bits.append(f'<span style="color:{dim}">(superseded)</span>')
    header = (f'<a name="m-{e.source_uuid}"></a>'
              f'<p style="color:{dim}; margin-bottom:2px">'
              + " &nbsp;·&nbsp; ".join(bits) + "</p>")
    if raw:
        size = float(theme.get("font-mono-size") or 11.0)
        body = (f'<pre style="font-family:\'{mono}\'; font-size:{size}pt; '
                f'margin-left:12px">{_html.escape(e.text)}</pre>')
    else:
        body = render_html(e.text, theme, mono).html
        body = linkify_ids(body, [u for u in jump_uuids if u != e.source_uuid])
        body = f'<div style="margin-left:12px">{body}</div>'
    return header + body


def build_timeline_html(entries: Sequence[TimelineEntry], theme: Dict, mono: str, *,
                        lane: str = "all", raw: bool = False,
                        selected: Sequence[str] = (), editing: Optional[str] = None,
                        expanded: Optional[Set[int]] = None) -> str:
    """The whole timeline document: cards separated by rules, consecutive
    superseded transcript runs collapsed behind an expandable chip
    (671e9b11 pt 8 — dead branches stay real, just folded)."""
    expanded = expanded or set()
    dim = theme.get("content-dim", "#888888")
    visible = lane_filter(entries, lane)
    if not visible:
        return (f'<p style="color:{dim}">no messages yet — the watcher pulls '
                f'the transcript as the session runs; Ctrl+Enter commits a part</p>')
    jump_uuids = [e.source_uuid for e in entries]
    out: List[str] = []
    for index, (kind, run) in enumerate(timeline_blocks(visible)):
        if kind == "superseded" and index not in expanded:
            out.append(f'<p><a href="branch://{index}" style="color:{dim}">'
                       f'⑂ {len(run)} superseded message(s) — expand</a></p><hr/>')
            continue
        if kind == "superseded":
            out.append(f'<p><a href="branch://{index}" style="color:{dim}">'
                       f'⑂ collapse superseded run</a></p>')
        for e in run:
            out.append(card_html(e, theme, mono, raw=raw, selected=selected,
                                 editing=editing, jump_uuids=jump_uuids))
            out.append("<hr/>")
    return "\n".join(out)
