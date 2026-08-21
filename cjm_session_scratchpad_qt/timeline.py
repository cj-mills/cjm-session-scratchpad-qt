"""Interleaved timeline derivation — the pure half of the v2 reading view.

One chronological timeline over BOTH chains (DEC 671e9b11 pt 1): transcript
messages (pulled, read-only) and composition parts (editor-born, editable in
place) merge by capture timestamp. The transcript chain is an append-only DAG
(pt 8): NEXT edges mirror capture succession and a rewind point simply has two
outgoing NEXT edges, so the ACTIVE PATH is derived here by walking back from
the tip (the newest transcript message is always on it) — rolled-back messages
stay real entries, marked off-path, and the widget collapses consecutive
off-path runs behind an expandable chip. Editability rides BIRTH CLASS
(pt 3), and `sent` marks a composition part consumed by a compose-send
(inbound DERIVED_FROM — the fc6a0cdc pt-5 aggregation seam)."""

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

# The composer birth class (mirrors the projection lib's MESSAGE_SOURCE_COMPOSER;
# duplicated as a plain string so this module stays import-light and pure).
COMPOSER_SOURCE = "composer"


@dataclass
class TimelineEntry:
    """One timeline row, presentation-ready."""
    node_id: str          # The Message node id (visible/copyable — 671e9b11 pt 4)
    source_uuid: str      # Capture-source identity (edit/derive verbs key on it)
    role: str             # "user" | "assistant"
    source: str           # Birth class: "cc-transcript" | "composer" | future sources
    text: str             # Raw markdown body (the authoritative content)
    timestamp: str        # ISO-8601 capture time ("" tolerated, sorts first)
    editable: bool        # Composer parts edit in place; pulled messages are read-only
    on_active_path: bool  # Transcript: derived tip-walk membership; composer: always True
    sent: bool            # Composition part with an inbound DERIVED_FROM


def build_timeline(
    messages: Sequence[Dict],            # Message property dicts: {id, source_uuid, role, text, timestamp, source}
    next_pairs: Sequence[Tuple[str, str]],     # NEXT edges as (source_node_id, target_node_id)
    derived_pairs: Sequence[Tuple[str, str]],  # DERIVED_FROM edges as (sent_node_id, part_node_id)
) -> List[TimelineEntry]:
    """Derive the interleaved timeline: active-path status + birth-class flags,
    chronological (stable on ties, so mint order holds within a timestamp)."""
    active = _active_transcript_ids(messages, next_pairs)
    sent_ids = {part for _sent, part in derived_pairs}
    entries: List[TimelineEntry] = []
    for m in messages:
        composer = m.get("source") == COMPOSER_SOURCE
        entries.append(TimelineEntry(
            node_id=m["id"], source_uuid=str(m.get("source_uuid") or ""),
            role=str(m.get("role") or ""), source=str(m.get("source") or ""),
            text=str(m.get("text") or ""), timestamp=str(m.get("timestamp") or ""),
            editable=composer,
            on_active_path=True if composer else (m["id"] in active),
            sent=m["id"] in sent_ids,
        ))
    entries.sort(key=lambda e: e.timestamp)  # ISO-8601 UTC Z sorts lexicographically; stable
    return entries


def _active_transcript_ids(
    messages: Sequence[Dict],
    next_pairs: Sequence[Tuple[str, str]],
) -> set:
    """Walk back from the transcript tip along (unique) inbound NEXT edges.

    Forks are OUTBOUND (a rewind point has two successors); every node has at
    most one predecessor, so the tip's ancestry IS the active path. A dangling
    predecessor or cycle ends the walk rather than raising (671e9b11 pt 8's
    defensive stance — the chain is reconstructed external history)."""
    transcript = [m for m in messages if m.get("source") != COMPOSER_SOURCE]
    if not transcript:
        return set()
    ids = {m["id"] for m in transcript}
    tip = max(transcript, key=lambda m: str(m.get("timestamp") or ""))["id"]
    pred = {dst: src for src, dst in next_pairs if dst in ids and src in ids}
    active = set()
    node = tip
    while node is not None and node not in active:
        active.add(node)
        node = pred.get(node)
    return active


def timeline_blocks(
    entries: Sequence[TimelineEntry],
) -> List[Tuple[str, List[TimelineEntry]]]:
    """Group consecutive off-path entries for the superseded-branch chip:
    [("live", [entries...]), ("superseded", [entries...]), ...] in order."""
    blocks: List[Tuple[str, List[TimelineEntry]]] = []
    for e in entries:
        kind = "live" if e.on_active_path else "superseded"
        if blocks and blocks[-1][0] == kind:
            blocks[-1][1].append(e)
        else:
            blocks.append((kind, [e]))
    return blocks
