"""Wrap-selection formatting operators (scope DEC 2a062aff pt 4) + the v2
block gestures (DEC 671e9b11 pt 6: ordered/unordered lists and multi-line
code fences).

The corpus-evidence cut: bold / italic / inline-code as marker wraps on the
current selection, toggling OFF when the selection (or its surroundings)
already carries the marker. No selection -> an empty pair with the caret
inside. Block gestures expand to whole lines and toggle likewise. Pure text
logic; the shell applies results through one QTextCursor edit block so undo
stays a single step."""

import re
from dataclasses import dataclass


@dataclass
class WrapResult:
    text: str        # replacement for the affected span
    start: int       # span start in the original document
    end: int         # span end in the original document
    cursor: int      # caret position after the edit
    anchor: int      # selection anchor after the edit (== cursor when none)


def wrap_selection(document: str, start: int, end: int, marker: str) -> WrapResult:
    """Toggle `marker` around [start, end) of `document`."""
    n = len(marker)
    selected = document[start:end]
    if start == end:
        return WrapResult(marker + marker, start, end,
                          cursor=start + n, anchor=start + n)
    if selected.startswith(marker) and selected.endswith(marker) \
            and len(selected) >= 2 * n:
        inner = selected[n:-n]
        return WrapResult(inner, start, end,
                          cursor=start + len(inner), anchor=start)
    if document[max(0, start - n):start] == marker and document[end:end + n] == marker:
        return WrapResult(selected, start - n, end + n,
                          cursor=start - n + len(selected), anchor=start - n)
    return WrapResult(marker + selected + marker, start, end,
                      cursor=end + 2 * n, anchor=start)


def _line_span(document: str, start: int, end: int) -> tuple:
    """Expand [start, end) to whole lines: (line_start, line_end) exclusive
    of the trailing newline."""
    ls = document.rfind("\n", 0, start) + 1
    le = document.find("\n", end)
    if le == -1:
        le = len(document)
    return ls, le


def fence_selection(document: str, start: int, end: int,
                    language: str = "") -> WrapResult:
    """Toggle a code fence around the selected lines. An already-fenced block
    unwraps; an empty selection opens a fence with the caret on its blank
    content line, ready to type."""
    ls, le = _line_span(document, start, end)
    block = document[ls:le]
    lines = block.split("\n")
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        inner = "\n".join(lines[1:-1])
        return WrapResult(inner, ls, le, cursor=ls + len(inner), anchor=ls)
    opener = f"```{language}"
    if block.strip():
        text = f"{opener}\n{block}\n```"
        caret = ls + len(opener) + 1 + len(block)
        return WrapResult(text, ls, le, cursor=caret, anchor=caret)
    text = f"{opener}\n\n```"
    caret = ls + len(opener) + 1
    return WrapResult(text, ls, le, cursor=caret, anchor=caret)


_UL_RE = re.compile(r"^(\s*)- ")
_OL_RE = re.compile(r"^(\s*)\d+\. ")


def toggle_list(document: str, start: int, end: int,
                ordered: bool = False) -> WrapResult:
    """Toggle list markers on the selected lines: strip when every non-blank
    line already carries the requested kind, otherwise (re)apply — converting
    the other kind in place. Ordered lists renumber from 1."""
    ls, le = _line_span(document, start, end)
    lines = document[ls:le].split("\n")
    rx = _OL_RE if ordered else _UL_RE
    content = [l for l in lines if l.strip()]
    if content and all(rx.match(l) for l in content):
        new_lines = [rx.sub(r"\1", l, count=1) if l.strip() else l for l in lines]
    else:
        def stripped(l: str) -> str:
            return _OL_RE.sub(r"\1", _UL_RE.sub(r"\1", l, count=1), count=1)
        n = 0
        new_lines = []
        for l in lines:
            if not l.strip():
                new_lines.append(l)
                continue
            n += 1
            base = stripped(l)
            indent = re.match(r"\s*", base).group(0)
            body = base[len(indent):]
            new_lines.append(f"{indent}{n}. {body}" if ordered else f"{indent}- {body}")
    text = "\n".join(new_lines)
    return WrapResult(text, ls, le, cursor=ls + len(text), anchor=ls)
