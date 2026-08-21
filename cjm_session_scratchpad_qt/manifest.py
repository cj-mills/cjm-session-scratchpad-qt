"""Pending-send manifests + pull-time reconciliation (DEC fc6a0cdc pt 5).

Compose-send is clipboard-transport with ZERO Claude Code integration: the app
concatenates the selected committed parts, copies the result as the outgoing
message, and records a pending-send manifest (part uuids + order + the exact
text). When the watcher later pulls the transcript, reconciliation matches
each manifest against the pulled USER messages: an exact text match auto-mints
the DERIVED_FROM aggregation edges; anything less stays pending — the future
HITL proposal lane (worklist doctrine), never a silent guess.

Manifests are session-scoped app state, stored as a JSON sidecar next to the
session's scratchpad artifacts (atomic writes, same discipline as files.py)."""

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

# Parts join as markdown paragraphs — the concatenation IS the outgoing message.
PART_JOINER = "\n\n"


@dataclass
class PendingSend:
    """One recorded compose-send awaiting its transcript echo."""
    part_uuids: List[str]            # Composition-part uuids, send order
    text: str                        # The exact concatenation copied out
    created_at: float = field(default_factory=time.time)


def compose_text(part_texts: Sequence[str]) -> str:
    """The outgoing message: parts joined as paragraphs, outer whitespace trimmed."""
    return PART_JOINER.join(t.strip() for t in part_texts).strip()


def manifest_path(directory: Path, session_key: str) -> Path:
    """The session's pending-send sidecar."""
    return Path(directory) / f"{session_key}.pending-send.json"


def load_pending(path: Path) -> List[PendingSend]:
    """Read manifests; a missing or unreadable sidecar is an empty list."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: List[PendingSend] = []
    for d in raw if isinstance(raw, list) else []:
        if isinstance(d, dict) and d.get("part_uuids") and "text" in d:
            out.append(PendingSend(part_uuids=list(d["part_uuids"]), text=str(d["text"]),
                                   created_at=float(d.get("created_at") or 0.0)))
    return out


def save_pending(path: Path, pending: Sequence[PendingSend]) -> None:
    """Persist manifests atomically (temp + rename; a concurrent read never
    sees a torn sidecar)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps([asdict(p) for p in pending], indent=2), encoding="utf-8")
    os.replace(tmp, path)


def reconcile(
    pending: Sequence[PendingSend],
    user_messages: Sequence[Dict],   # Pulled USER messages: {source_uuid, text}
) -> Tuple[List[Tuple[str, List[str]]], List[PendingSend]]:
    """Match manifests against pulled user messages by EXACT text.

    Returns (derivations, remaining): each derivation is (sent_uuid,
    part_uuids) ready for the derive-message verb; unmatched manifests stay
    pending — near-match promotion to an HITL proposal is a later rung, never
    an auto-mint here."""
    derivations: List[Tuple[str, List[str]]] = []
    remaining: List[PendingSend] = []
    claimed: set = set()
    for p in pending:
        hit = next((m for m in user_messages
                    if m.get("source_uuid") not in claimed
                    and str(m.get("text") or "").strip() == p.text.strip()), None)
        if hit is not None:
            claimed.add(hit.get("source_uuid"))
            derivations.append((str(hit.get("source_uuid")), list(p.part_uuids)))
        else:
            remaining.append(p)
    return derivations, remaining
