"""One open graph behind the scratchpad — the workbench GraphSession pattern
wholesale (DEC 93e3e881): open_graph ONCE behind a private asyncio loop
thread, sync blocking fetches for the Qt widgets, writes journal-first in
cg-write's EXACT arg shape as actor `user:scratchpad` so replay/rebuild treats
app writes and cg-writes identically. Reads are ambient for free (open_graph
declares graph-storage ambient — timeline reads at UI cadence produce zero
success-accounting rows), and the pull watcher calls pull_transcript()
in-process: nothing new = nothing journaled, the watcher-cadence guarantee."""

import os
import re
import uuid as uuidlib
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cjm_context_graph_layer.ops import graph_task
from cjm_context_graph_primitives.journal import append_write
from cjm_context_graph_primitives.query import EdgeQuery, PropertyPredicate
from cjm_context_graph_projection.factlayer import load_label_where
from cjm_context_graph_projection.pull_transcript import (derive_message, edit_message,
                                                          MESSAGE_SOURCE_COMPOSER,
                                                          mint_pulled_messages, pull_transcript)
from cjm_context_graph_projection.runtime import DEFAULT_MANIFESTS, open_graph
from cjm_context_graph_projection.scratchpad_export import export_session_markdown
from cjm_substrate_qt_kit.loopthread import LoopThreadSession

# Per-actor stamping (DEC c7c6ce5e; user:workbench is the precedent).
ACTOR = "user:scratchpad"


def default_transcript_dir(project_dir: Path) -> Path:
    """The harness transcript dir for a project: `~/.claude/projects/<slug>`,
    the slug being the project path with every non-alphanumeric flattened to
    `-` (the harness's own encoding)."""
    slug = re.sub(r"[^A-Za-z0-9-]", "-", str(project_dir))
    return Path.home() / ".claude" / "projects" / slug


def part_payload(text: str, prev_uuid: Optional[str]) -> Dict[str, Any]:
    """A composer part's mint/journal payload: composer-minted uuid (the
    message_node_id identity contract), UTC capture stamp, composer source."""
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return {"uuid": uuidlib.uuid4().hex, "parent_uuid": None, "prev_uuid": prev_uuid,
            "role": "user", "text": text, "timestamp": ts.replace("+00:00", "Z"),
            "source": MESSAGE_SOURCE_COMPOSER}


class ScratchpadSession(LoopThreadSession):
    """Sync facade over the projection layer for ONE session's scratchpad:
    start() opens the graph and adopts the session key (CJM_SESSION — the app
    knows its key by construction, so every journaled write is stamped),
    the fetch/commit methods block the caller, close() tears down."""

    thread_name = "scratchpad-graph"

    def __init__(self, graph_db_path: str, session_key: str,
                 manifests_dir: Optional[str] = None,
                 journal_paths: Optional[List[str]] = None, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.graph_db_path = graph_db_path
        self.session_key = session_key
        self.manifests_dir = manifests_dir or DEFAULT_MANIFESTS
        self.journal_paths = list(journal_paths or [])
        self.gx = None
        self._stack: Optional[AsyncExitStack] = None

    async def _open(self):
        self._stack = AsyncExitStack()
        return await self._stack.enter_async_context(
            open_graph(self.graph_db_path, self.manifests_dir))

    def start(self) -> None:
        super().start()
        os.environ["CJM_SESSION"] = self.session_key  # journal appends stamp this key
        self.gx = self.call(self._open())

    # ---- reads (ambient — no accounting rows at UI cadence) --------------

    async def _timeline_data(self) -> Tuple[List[Dict], List[Tuple[str, str]], List[Tuple[str, str]]]:
        """The timeline's raw material: this session's Message property dicts
        + the NEXT and DERIVED_FROM edges among them."""
        nodes = await load_label_where(
            self.gx, "Message",
            [PropertyPredicate("session_key", "eq", self.session_key)], limit=100000)
        messages: List[Dict] = []
        for n in nodes:
            props = dict((n.get("properties") if isinstance(n, dict)
                          else getattr(n, "properties", None)) or {})
            props["id"] = n.get("id") if isinstance(n, dict) else getattr(n, "id", None)
            messages.append(props)
        ids = [m["id"] for m in messages if m.get("id")]
        next_pairs = await self._edge_pairs("NEXT", source_ids=ids)
        derived_pairs = await self._edge_pairs("DERIVED_FROM", target_ids=ids)
        return messages, next_pairs, derived_pairs

    async def _edge_pairs(self, relation: str, source_ids: Optional[List[str]] = None,
                          target_ids: Optional[List[str]] = None) -> List[Tuple[str, str]]:
        if not (source_ids or target_ids):
            return []
        q = EdgeQuery(relation_type=relation, source_ids=source_ids,
                      target_ids=target_ids, project=["id"])
        res = await graph_task(self.gx.queue, self.gx.graph_id, "query_edges",
                               query=q.to_dict())
        return [(r["source_id"], r["target_id"]) for r in (res.rows or [])]

    def timeline_data(self):
        """Blocking read (construction / gesture refresh)."""
        return self.call(self._timeline_data())

    def timeline_data_async(self):
        """Non-blocking read for watcher-cadence refresh — the Qt shell must
        never block its paint thread on a graph read (drive find 2026-08-14)."""
        return self.submit(self._timeline_data())

    # ---- journaled writes (cg-write's exact arg shape) -------------------

    def _journal(self, verb: str, args: Dict[str, Any]) -> None:
        """Mirror a LANDED write into the writes journal (journal_paths[0]) —
        an unjournaled write is lost on the next rebuild (the db is a
        projection)."""
        if self.journal_paths:
            append_write(self.journal_paths[0], verb, args)

    def commit_part(self, text: str, prev_uuid: Optional[str] = None) -> Dict[str, Any]:
        """Mint one committed composition part on the session spine (the same
        source-agnostic mint machinery as the pull — DEC 93e3e881 pt 5)."""
        payload = part_payload(text, prev_uuid)
        res = self.call(mint_pulled_messages(self.gx, self.session_key, "",
                                             [payload], actor=ACTOR))
        if res.get("written"):
            self._journal("mint-messages", {"session_key": self.session_key,
                                            "messages": [payload], "actor": ACTOR})
        return {**res, "payload": payload}

    def edit_part(self, source_uuid: str, text: str) -> Dict[str, Any]:
        """Journaled in-place body edit of a composer part (editability by
        birth class — pulled messages never route here)."""
        res = self.call(edit_message(self.gx, source_uuid, text, actor=ACTOR))
        if res.get("written"):
            self._journal("edit-message", {"source_uuid": source_uuid,
                                           "text": text, "actor": ACTOR})
        return res

    def record_send(self, sent_uuid: str, part_uuids: List[str]) -> Dict[str, Any]:
        """Land a reconciled compose-send: DERIVED_FROM edges sent -> parts,
        send order on the edge properties."""
        res = self.call(derive_message(self.gx, sent_uuid, part_uuids, actor=ACTOR))
        if res.get("written"):
            self._journal("derive-message", {"sent_uuid": sent_uuid,
                                             "part_uuids": list(part_uuids),
                                             "actor": ACTOR})
        return res

    def export_markdown(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """The exporter lens in-process (item 5ab24c57): the session's message
        graph as portable markdown. Read-only — journals nothing; an edited
        export is a fork, never a sync."""
        return self.call(export_session_markdown(self.gx, self.session_key, config))

    # ---- the pull path (watcher-primary; gesture = backfill) -------------

    async def _pull(self, transcript_dir: str, require_signal: bool) -> Dict[str, Any]:
        res = await pull_transcript(self.gx, self.session_key, transcript_dir,
                                    require_signal=require_signal, actor=ACTOR)
        if not res.get("error") and res.get("new_messages"):
            # The CLI's exact journal shape (self-contained replay payload);
            # a quiet pull journals NOTHING — the watcher-cadence guarantee.
            self._journal("pull-transcript",
                          {"session_key": self.session_key,
                           "cc_session_uuid": res.get("cc_session_uuid", ""),
                           "messages": res["new_messages"], "actor": ACTOR})
        return res

    def pull(self, transcript_dir: str, require_signal: bool = True) -> Dict[str, Any]:
        """Blocking pull (the in-session backfill gesture)."""
        return self.call(self._pull(transcript_dir, require_signal))

    def pull_async(self, transcript_dir: str, require_signal: bool = True):
        """Non-blocking pull for the watcher tick; resolves to the pull result."""
        return self.submit(self._pull(transcript_dir, require_signal))

    async def on_close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
