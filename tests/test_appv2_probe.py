"""V2 shell probe (offscreen): timeline render, part commit + edit flows,
compose-send manifest + reconciliation, link routing, lane/raw toggles —
over a fake session (the graph seam itself is field-proven live)."""

import os
import uuid as uuidlib
from concurrent.futures import Future

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from cjm_session_scratchpad_qt.appv2 import GraphScratchpadWindow
from cjm_session_scratchpad_qt.manifest import load_pending, manifest_path

KEY = "2026-08-21_11-26-36"


def msg(nid, uuid, ts, role="user", source="cc-transcript", text="hello"):
    return {"id": nid, "source_uuid": uuid, "role": role, "text": text,
            "timestamp": ts, "source": source}


class FakeSession:
    """Duck-typed ScratchpadSession: records writes, serves canned reads."""
    session_key = KEY

    def __init__(self, messages=None, next_pairs=None, derived=None):
        self.messages = messages or []
        self.next_pairs = next_pairs or []
        self.derived = derived or []
        self.committed = []
        self.edited = []
        self.sends = []

    def timeline_data(self):
        return self.messages, self.next_pairs, self.derived

    def timeline_data_async(self):
        f = Future()
        f.set_result(self.timeline_data())
        return f

    def commit_part(self, text, prev_uuid=None):
        payload = {"uuid": uuidlib.uuid4().hex, "prev_uuid": prev_uuid,
                   "role": "user", "text": text,
                   "timestamp": "2026-08-21T12:00:00.000Z", "source": "composer"}
        self.committed.append(payload)
        self.messages.append(msg(f"node-{payload['uuid']}", payload["uuid"],
                                 payload["timestamp"], source="composer", text=text))
        return {"written": True, "payload": payload}

    def edit_part(self, source_uuid, text):
        self.edited.append((source_uuid, text))
        for m in self.messages:
            if m["source_uuid"] == source_uuid:
                m["text"] = text
        return {"written": True}

    def record_send(self, sent_uuid, part_uuids):
        self.sends.append((sent_uuid, list(part_uuids)))
        return {"written": True}

    def pull_async(self, transcript_dir, require_signal=True):
        f = Future()
        f.set_result({"messages_new": 0, "messages_total": len(self.messages),
                      "new_messages": []})
        return f


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make(app, tmp_path, session=None):
    session = session or FakeSession(
        messages=[msg("n1", "u1", "2026-08-21T10:00:00.000Z"),
                  msg("n2", "a1", "2026-08-21T10:01:00.000Z", role="assistant",
                      text="reply **strong**")],
        next_pairs=[("n1", "n2")])
    window = GraphScratchpadWindow(session, transcript_dir=tmp_path / "transcripts",
                                   directory=tmp_path)
    return session, window


def test_initial_timeline_renders_both_roles(app, tmp_path):
    _s, w = make(app, tmp_path)
    text = w.browser.toPlainText()
    assert "YOU" in text and "CLAUDE" in text
    assert "strong" in text


def test_commit_part_threads_prev_uuid_and_clears(app, tmp_path):
    s, w = make(app, tmp_path)
    w.composer.setPlainText("first part")
    w.commit_part()
    w.composer.setPlainText("second part")
    w.commit_part()
    assert [p["prev_uuid"] for p in s.committed] == [None, s.committed[0]["uuid"]]
    assert w.composer.toPlainText() == ""
    w._resolve_futures()
    assert "PART" in w.browser.toPlainText()


def test_edit_flow_routes_to_edit_part(app, tmp_path):
    s, w = make(app, tmp_path)
    w.composer.setPlainText("draft")
    w.commit_part()
    w._resolve_futures()
    part_uuid = s.committed[0]["uuid"]
    w._on_link(QUrl(f"edit://{part_uuid}"))
    assert w.composer.toPlainText() == "draft"
    w.composer.setPlainText("draft, revised")
    w.commit_part()
    assert s.edited == [(part_uuid, "draft, revised")]
    assert w._editing is None


def test_compose_send_copies_and_manifests(app, tmp_path):
    s, w = make(app, tmp_path)
    for text in ("one", "two"):
        w.composer.setPlainText(text)
        w.commit_part()
    w._resolve_futures()
    for p in s.committed:
        w._on_link(QUrl(f"sel://{p['uuid']}"))
    w.compose_send()
    assert QApplication.clipboard().text() == "one\n\ntwo"
    pending = load_pending(manifest_path(tmp_path, KEY))
    assert [p.part_uuids for p in pending] == [[s.committed[0]["uuid"],
                                                s.committed[1]["uuid"]]]
    assert w._selected == []


def test_pull_result_reconciles_manifest_into_send(app, tmp_path):
    s, w = make(app, tmp_path)
    for text in ("one", "two"):
        w.composer.setPlainText(text)
        w.commit_part()
    w._resolve_futures()
    for p in s.committed:
        w._on_link(QUrl(f"sel://{p['uuid']}"))
    w.compose_send()
    w._on_pull_result({"messages_new": 1, "messages_total": 3,
                       "new_messages": [{"uuid": "u9", "role": "user",
                                         "text": "one\n\ntwo",
                                         "timestamp": "2026-08-21T12:05:00.000Z"}]})
    assert s.sends == [("u9", [s.committed[0]["uuid"], s.committed[1]["uuid"]])]
    assert load_pending(manifest_path(tmp_path, KEY)) == []


def test_startup_reconciles_prior_run_manifest(app, tmp_path):
    # A send recorded before an app restart matches a message already on-graph.
    from cjm_session_scratchpad_qt.manifest import PendingSend, save_pending
    save_pending(manifest_path(tmp_path, KEY),
                 [PendingSend(part_uuids=["c1"], text="hello")])
    s = FakeSession(messages=[msg("n1", "u1", "2026-08-21T10:00:00.000Z", text="hello")])
    _s, w = make(app, tmp_path, session=s)
    assert s.sends == [("u1", ["c1"])]


def test_copy_link_puts_node_id_on_clipboard(app, tmp_path):
    _s, w = make(app, tmp_path)
    w._on_link(QUrl("copy://n1"))
    assert QApplication.clipboard().text() == "n1"


def test_lane_and_raw_toggles_change_document(app, tmp_path):
    _s, w = make(app, tmp_path)
    w.cycle_lane()  # -> composition (no parts yet: placeholder text)
    assert "no messages yet" in w.browser.toPlainText()
    w.cycle_lane()  # -> transcript
    assert "CLAUDE" in w.browser.toPlainText()
    w.cycle_lane()  # -> all
    w.toggle_raw()
    assert "**strong**" in w.browser.toPlainText()


def test_dup_lane_toggles_visibility(app, tmp_path):
    _s, w = make(app, tmp_path)
    assert w.dup_browser.isHidden()
    w.toggle_dup()
    assert not w.dup_browser.isHidden()
