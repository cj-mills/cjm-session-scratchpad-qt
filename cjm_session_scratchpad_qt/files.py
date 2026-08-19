"""Session-aware file resolution (DEC ea85eab7 pts 1-2).

No-arg launch walks UP from cwd for `.cjm/current-session` (marker-rooted
spirit) and binds `<key>.md` in the scratchpad dir, creating it blank when
new — with key-based naming this kills both halves of the manual lifecycle
(copy-previous + rename rituals). Pointer absent -> the most recent
scratchpad plus a visible banner, never a silently wrongly-named file; a
key whose timestamp is not from today banners its age (dissolves once the
UI can mint sessions like the workbench). An explicit path argument opens
any file — previous sessions, or the standing `_carryover.md`."""

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

SCRATCHPAD_DIR = Path.home() / "Downloads" / "claude-code-scratchpads"
KEY_FORMAT = "%Y-%m-%d_%H-%M-%S"


@dataclass
class Target:
    path: Path
    banner: Optional[str] = None  # visible, never blocking


def find_session_key(start: Path) -> Optional[str]:
    """Walk up from `start` for the nearest `.cjm/current-session` pointer."""
    for directory in [start, *start.parents]:
        pointer = directory / ".cjm" / "current-session"
        if pointer.is_file():
            key = pointer.read_text().strip()
            if key:
                return key
    return None


def parse_key_time(key: str) -> Optional[datetime]:
    """A session key is its mint timestamp; None for legacy/free-form names."""
    try:
        return datetime.strptime(key, KEY_FORMAT)
    except ValueError:
        return None


def most_recent(directory: Path) -> Optional[Path]:
    """Newest markdown file by mtime (the absent-pointer fallback)."""
    candidates = [p for p in directory.glob("*.md") if p.is_file()]
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


def resolve_target(cwd: Path, arg: Optional[str] = None,
                   directory: Optional[Path] = None,
                   today: Optional[date] = None) -> Target:
    """The launch contract: explicit path wins; otherwise the session
    pointer's file (created blank by the caller when new); otherwise the
    most recent scratchpad, bannered."""
    directory = directory or SCRATCHPAD_DIR
    if arg:
        return Target(Path(arg).expanduser())
    key = find_session_key(cwd)
    if key is None:
        fallback = most_recent(directory)
        if fallback is None:
            return Target(directory / "untitled.md",
                          banner="no .cjm/current-session pointer found — new untitled file")
        return Target(fallback,
                      banner="no .cjm/current-session pointer found — opened most recent scratchpad")
    path = directory / f"{key}.md"
    minted = parse_key_time(key)
    if minted is not None and minted.date() != (today or date.today()):
        return Target(path, banner=f"session key minted {minted:%Y-%m-%d %H:%M} — pointer may be stale")
    return Target(path)


def ensure_file(path: Path) -> bool:
    """Create the file blank if missing (sessions are born blank now);
    returns True when it was created."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return True


def atomic_write(path: Path, text: str) -> None:
    """temp + rename in the target dir: a mid-session agent read never sees
    a torn file (DEC ea85eab7 pt 3)."""
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
