"""The owned markdown -> HTML pipeline (DEC ea85eab7 pt 4).

Owning the pipeline is what buys position stability: every block element
carries an `<a name="Lxx">` anchor naming its 0-based source line, so the
shell can map the top-visible position across the edit<->render toggle in
both directions (the Typora gripe this seat exists to delete). Feature set
is corpus-evidence-driven (scope DEC 2a062aff pt 4): headings, fenced code,
blockquotes, hr, nested bullet/numbered lists, pipe tables, and the inline
trio bold/italic/code plus links. Pure text -> text; Qt never imports here.

One deliberate divergence from CommonMark: single newlines inside a
paragraph render as line breaks (chat-renderer convention) — scratchpad
messages carry pasted CLI output and intentional line structure that
soft-break joining would mangle."""

import html as _html
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^\s{0,3}(```+|~~~+)\s*(.*)$")
_HR = re.compile(r"^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$")
_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD_STAR = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*")
_BOLD_UNDER = re.compile(r"(?<![0-9A-Za-z_])__(?!\s)(.+?)(?<!\s)__(?![0-9A-Za-z_])")
_ITAL_STAR = re.compile(r"\*(?!\s)([^*]+?)(?<!\s)\*")
_ITAL_UNDER = re.compile(r"(?<![0-9A-Za-z_])_(?!\s)([^_]+?)(?<!\s)_(?![0-9A-Za-z_])")


@dataclass
class RenderResult:
    html: str
    anchor_lines: List[int]  # 0-based source lines carrying anchors, ascending


def nearest_anchor(anchor_lines: List[int], line: int) -> Optional[int]:
    """The anchor line for a source position: greatest anchor <= line
    (first anchor when the position precedes them all)."""
    if not anchor_lines:
        return None
    best = anchor_lines[0]
    for candidate in anchor_lines:
        if candidate > line:
            break
        best = candidate
    return best


def render_html(text: str, tokens: Optional[Dict] = None,
                mono_family: str = "monospace") -> RenderResult:
    """Render markdown to QTextBrowser-ready HTML with per-block source-line
    anchors. `tokens` is a theme dict (raised / border / accent /
    font-mono-size are read, all with fallbacks); `mono_family` is the
    resolved code font family."""
    return _Renderer(tokens or {}, mono_family).run(text)


class _Renderer:
    def __init__(self, tokens: Dict, mono_family: str):
        self.raised = tokens.get("raised", "#eeeeee")
        self.border = tokens.get("border", "#bbbbbb")
        self.mono_size = float(tokens.get("font-mono-size") or 11.0)
        self.mono = mono_family
        self.anchors: List[int] = []

    def run(self, text: str) -> RenderResult:
        lines = text.split("\n")
        out: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            fence = _FENCE.match(line)
            if fence:
                i = self._code_block(lines, i, fence.group(1), out)
                continue
            heading = _HEADING.match(line)
            if heading:
                level = len(heading.group(1))
                out.append(f"<h{level}>{self._anchor(i)}"
                           f"{self._inline(heading.group(2))}</h{level}>")
                i += 1
                continue
            if _HR.match(line):
                # no anchor: <hr> holds no fragment, so a name would be
                # unreachable for scrollToAnchor — the previous block covers it
                out.append("<hr/>")
                i += 1
                continue
            if _QUOTE.match(line):
                i = self._blockquote(lines, i, out)
                continue
            if _ITEM.match(line):
                i = self._list(lines, i, out)
                continue
            if "|" in line and i + 1 < len(lines) and "|" in lines[i + 1] \
                    and _TABLE_SEP.match(lines[i + 1]):
                i = self._table(lines, i, out)
                continue
            i = self._paragraph(lines, i, out)
        return RenderResult("\n".join(out), list(self.anchors))

    def _anchor(self, line: int) -> str:
        self.anchors.append(line)
        return f'<a name="L{line}"></a>'

    def _code_block(self, lines: List[str], i: int, fence: str,
                    out: List[str]) -> int:
        start = i
        i += 1
        body: List[str] = []
        while i < len(lines):
            closing = _FENCE.match(lines[i])
            if closing and closing.group(1)[0] == fence[0] \
                    and len(closing.group(1)) >= len(fence) and not closing.group(2):
                i += 1
                break
            body.append(lines[i])
            i += 1
        escaped = _html.escape("\n".join(body))
        # Qt renders bare <pre> unwrapped (long lines force a horizontal
        # scroll) and paints background per-character; a one-cell table gives
        # the full-width block box, pre-wrap keeps prose-bearing fences on
        # screen (field finding 2026-08-19).
        out.append(f'<table width="100%" cellspacing="0" cellpadding="6" '
                   f'bgcolor="{self.raised}"><tr><td bgcolor="{self.raised}">'
                   f"<pre style=\"white-space:pre-wrap; "
                   f"font-family:'{self.mono}'; font-size:{self.mono_size}pt;\">"
                   f"{self._anchor(start)}{escaped}</pre></td></tr></table>")
        return i

    def _blockquote(self, lines: List[str], i: int, out: List[str]) -> int:
        start = i
        inner: List[str] = []
        while i < len(lines):
            m = _QUOTE.match(lines[i])
            if not m:
                break
            inner.append(m.group(1))
            i += 1
        # Inner content re-renders as its own block run; anchors inside would
        # collide with outer numbering, so the quote carries one anchor and
        # the inner renderer's are dropped.
        sub = _Renderer({"raised": self.raised, "border": self.border,
                         "font-mono-size": self.mono_size}, self.mono)
        inner_html = sub.run("\n".join(inner)).html
        inner_html = re.sub(r'<a name="L\d+"></a>', "", inner_html)
        out.append(f"<blockquote>{self._anchor(start)}{inner_html}</blockquote>")
        return i

    def _list(self, lines: List[str], i: int, out: List[str]) -> int:
        stack: List[Tuple[int, str]] = []  # (indent, tag)
        parts: List[str] = []

        def open_list(indent: int, ordered: bool) -> None:
            tag = "ol" if ordered else "ul"
            stack.append((indent, tag))
            parts.append(f"<{tag}>")

        def close_to(indent: int) -> None:
            while stack and stack[-1][0] > indent:
                parts.append(f"</{stack.pop()[1]}>")

        while i < len(lines):
            m = _ITEM.match(lines[i])
            if not m:
                if not lines[i].strip():
                    peek = i + 1
                    while peek < len(lines) and not lines[peek].strip():
                        peek += 1
                    if peek < len(lines) and _ITEM.match(lines[peek]):
                        i = peek
                        continue
                break
            indent = len(m.group(1))
            ordered = m.group(2)[0].isdigit()
            if not stack or indent > stack[-1][0]:
                open_list(indent, ordered)
            else:
                close_to(indent)
                if not stack:
                    open_list(indent, ordered)
            parts.append(f"<li>{self._anchor(i)}{self._inline(m.group(3))}</li>")
            i += 1
        close_to(-1)
        out.append("".join(parts))
        return i

    def _table(self, lines: List[str], i: int, out: List[str]) -> int:
        def cells(row: str) -> List[str]:
            return [c.strip() for c in row.strip().strip("|").split("|")]
        header = cells(lines[i])
        rows: List[List[str]] = []
        j = i + 2
        while j < len(lines) and "|" in lines[j] and lines[j].strip():
            rows.append(cells(lines[j]))
            j += 1
        parts = [f'<table border="1" cellspacing="0" cellpadding="4" '
                 f'style="border-color:{self.border};">',
                 "<tr>" + "".join(f"<td><b>{self._inline(c)}</b></td>"
                                  for c in header) + "</tr>"]
        parts[1] = "<tr>" + self._anchor(i) + parts[1][4:]
        for row in rows:
            parts.append("<tr>" + "".join(f"<td>{self._inline(c)}</td>"
                                          for c in row) + "</tr>")
        parts.append("</table>")
        out.append("".join(parts))
        return j

    def _paragraph(self, lines: List[str], i: int, out: List[str]) -> int:
        start = i
        body: List[str] = []
        while i < len(lines) and lines[i].strip():
            if (_HEADING.match(lines[i]) or _FENCE.match(lines[i])
                    or _QUOTE.match(lines[i]) or _ITEM.match(lines[i])
                    or _HR.match(lines[i])) and i > start:
                break
            body.append(lines[i])
            i += 1
        rendered = "<br/>".join(self._inline(line) for line in body)
        out.append(f"<p>{self._anchor(start)}{rendered}</p>")
        return i

    def _inline(self, text: str) -> str:
        escaped = _html.escape(text, quote=False)
        spans: List[str] = []

        def stash(m: re.Match) -> str:
            spans.append(m.group(2))
            return f"\x00{len(spans) - 1}\x00"

        escaped = _CODE_SPAN.sub(stash, escaped)
        escaped = _LINK.sub(r'<a href="\2">\1</a>', escaped)
        escaped = _BOLD_STAR.sub(r"<b>\1</b>", escaped)
        escaped = _BOLD_UNDER.sub(r"<b>\1</b>", escaped)
        escaped = _ITAL_STAR.sub(r"<i>\1</i>", escaped)
        escaped = _ITAL_UNDER.sub(r"<i>\1</i>", escaped)
        for index, span in enumerate(spans):
            code = (f"<code style=\"background-color:{self.raised}; "
                    f"font-family:'{self.mono}'; font-size:{self.mono_size}pt;\">"
                    f"{span.strip()}</code>")
            escaped = escaped.replace(f"\x00{index}\x00", code)
        return escaped
