"""Transcript-dir change detection — the sleep-first mtime poll's pure half.

The live transcript JSONL is appended by the harness as the session runs
(DEC fc6a0cdc pt 4): the shell's QTimer tick asks `changed()` and only then
spends a pull. Nothing here touches the graph — a quiet tick costs one
directory scan, and the pull itself journals nothing when nothing is new
(the watcher-cadence guarantee lives in the pull verb)."""

from pathlib import Path
from typing import Dict, Tuple


class DirWatch:
    """Cheap (mtime, size) fingerprint over a transcript dir's *.jsonl."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._seen: Dict[str, Tuple[float, int]] = {}
        self._primed = False

    def _scan(self) -> Dict[str, Tuple[float, int]]:
        out: Dict[str, Tuple[float, int]] = {}
        try:
            for p in self.directory.glob("*.jsonl"):
                try:
                    st = p.stat()
                except OSError:
                    continue
                out[p.name] = (st.st_mtime, st.st_size)
        except OSError:
            pass
        return out

    def changed(self) -> bool:
        """True when any transcript appeared/grew/changed since the last ask.
        The FIRST ask always reports change (the startup backfill pull)."""
        now = self._scan()
        if not self._primed:
            self._primed = True
            self._seen = now
            return True
        if now != self._seen:
            self._seen = now
            return True
        return False
