"""Wrap-selection formatting operators (scope DEC 2a062aff pt 4).

The corpus-evidence cut: bold / italic / inline-code as marker wraps on the
current selection, toggling OFF when the selection (or its surroundings)
already carries the marker. No selection -> an empty pair with the caret
inside. Pure text logic; the shell applies results through one QTextCursor
edit block so undo stays a single step."""

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
