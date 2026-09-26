"""V2 shell probe (offscreen): timeline render, part commit + edit flows,
compose-send manifest + reconciliation, link routing, lane/raw toggles —
over a fake session (the graph seam itself is field-proven live)."""

import os
import uuid as uuidlib
from concurrent.futures import Future
from datetime import datetime

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
        self.by_key = {}     # optional per-spine canned messages (rebind swaps)
        self.adopted = []    # adopt=True rebind calls (mint gesture only)
        self.registered = []  # register_session calls (key, started_at, title)
        self.journal_paths = []  # the mint's pointer lands beside journal_paths[0]

    def register_session(self, key, *, started_at=None, title=None):
        self.registered.append((key, started_at, title))
        return {"written": True}

    def rebind(self, session_key, *, adopt=False):
        self.session_key = session_key
        if adopt:
            self.adopted.append(session_key)
        if session_key in self.by_key:
            self.messages = self.by_key[session_key]

    def list_sessions(self):
        keys = {self.session_key, *self.by_key}
        return [{"key": k, "title": ""} for k in sorted(keys, reverse=True)]

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

    def export_markdown(self, config=None):
        return {"text": f"# Session scratchpad — {KEY}\n\nexport body\n",
                "messages": len(self.messages), "parts": 0}


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


def test_edit_detour_preserves_in_flight_draft(app, tmp_path):
    # Drive call-out 2026-08-21: clicking edit on a part wiped the draft being
    # composed. The stash holds it across the detour — both exit doors.
    s, w = make(app, tmp_path)
    w.composer.setPlainText("committed part")
    w.commit_part()
    w._resolve_futures()
    part_uuid = s.committed[0]["uuid"]
    w.composer.setPlainText("half-written next part")
    w._on_link(QUrl(f"edit://{part_uuid}"))          # detour into edit mode
    assert w.composer.toPlainText() == "committed part"
    w.cancel_edit()                                   # exit door 1: cancel
    assert w.composer.toPlainText() == "half-written next part"
    w._on_link(QUrl(f"edit://{part_uuid}"))
    w.composer.setPlainText("committed part, revised")
    w.commit_part()                                   # exit door 2: edit lands
    assert s.edited == [(part_uuid, "committed part, revised")]
    assert w.composer.toPlainText() == "half-written next part"


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


def test_export_md_writes_projection_beside_scratchpads(app, tmp_path):
    _s, w = make(app, tmp_path)
    w.export_md()
    out = tmp_path / f"{KEY}.export.md"
    assert out.exists()
    assert out.read_text().startswith(f"# Session scratchpad — {KEY}")


def test_dup_lane_toggles_visibility(app, tmp_path):
    _s, w = make(app, tmp_path)
    assert w.dup_browser.isHidden()
    w.toggle_dup()
    assert not w.dup_browser.isHidden()


def test_open_past_session_rebinds_and_gates_watcher(app, tmp_path):
    # Item 4 (sitting 3): opening a past spine swaps the timeline, marks the
    # seat non-live (watcher spends nothing), and returning restores watching.
    s, w = make(app, tmp_path)
    assert w.is_live
    past = "2026-08-20_17-05-20"
    s.by_key = {past: [msg("p1", "x1", "2026-08-20T18:00:00.000Z", text="yesterday-msg")],
                KEY: list(s.messages)}
    w.rebind_spine(past)
    assert not w.is_live
    assert s.session_key == past
    assert s.adopted == []                      # browsing never re-stamps attribution
    assert "yesterday-msg" in w.browser.toPlainText()
    assert "(past)" in w.key_label.text()
    w._on_watch_tick()
    assert w._pull_future is None               # past spine: watcher off
    w.rebind_spine(KEY)
    assert w.is_live and "(past)" not in w.key_label.text()


def test_session_picker_filters_and_chooses(app, tmp_path):
    from cjm_session_scratchpad_qt.appv2 import SessionPickerDialog
    sessions = [{"key": "2026-08-21_20-46-05", "title": "sitting 3"},
                {"key": "2026-08-21_11-26-36", "title": "sitting 2"}]
    d = SessionPickerDialog(sessions, current="2026-08-21_20-46-05",
                            live="2026-08-21_20-46-05")
    assert d.listing.count() == 2
    assert "[live · open]" in d.listing.item(0).text()
    d.filter.setText("sitting 2")
    assert d.listing.count() == 1
    d._choose_current()
    assert d.chosen == "2026-08-21_11-26-36"


def test_scratchpad_session_rebind_attribution(monkeypatch):
    # The real ScratchpadSession.rebind: browsing keeps CJM_SESSION on the
    # live sitting; adopt=True (mint gesture) re-stamps it. No graph needed —
    # rebind is pure key/env state.
    from cjm_session_scratchpad_qt.graph import ScratchpadSession
    sess = ScratchpadSession("unused.db", "live-key")
    monkeypatch.setenv("CJM_SESSION", "live-key")
    sess.rebind("past-key")
    assert sess.session_key == "past-key"
    assert os.environ["CJM_SESSION"] == "live-key"
    sess.rebind("new-key", adopt=True)
    assert os.environ["CJM_SESSION"] == "new-key"


def test_mint_session_registers_adopts_and_arms_clipboard(app, tmp_path, monkeypatch):
    # Item 2 (sitting 3): the mint gesture registers a fresh spine, moves the
    # live key + pointer, adopts (attribution re-stamp recorded), and puts the
    # signal-bearing boot prompt on the clipboard.
    from cjm_session_scratchpad_qt import appv2
    s, w = make(app, tmp_path)
    s.journal_paths = [str(tmp_path / ".cjm" / "g.writes.jsonl")]
    monkeypatch.setattr(
        appv2.QMessageBox, "question",
        staticmethod(lambda *a, **k: appv2.QMessageBox.StandardButton.Yes))
    w.mint_session()
    assert len(s.registered) == 1
    key = s.registered[0][0]
    assert s.registered[0][1] is not None            # started_at rides the op
    assert w._live_key == key and s.session_key == key and w.is_live
    assert s.adopted == [key]                        # CJM_SESSION re-stamp path
    # the ONE mint (kit sessionkey) wrote the pointer beside the journal
    assert (tmp_path / ".cjm" / "current-session").read_text() == key
    boot = QApplication.clipboard().text()
    assert "New session minted in-scratchpad" in boot
    from cjm_harness_transcripts.mapping import MINT_SIGNAL
    assert MINT_SIGNAL in boot                       # transcript mapping will match


def test_mint_session_debounces_and_respects_decline(app, tmp_path, monkeypatch):
    from cjm_session_scratchpad_qt import appv2
    s, w = make(app, tmp_path)
    # Decline path: the dialog says no, nothing moves.
    monkeypatch.setattr(
        appv2.QMessageBox, "question",
        staticmethod(lambda *a, **k: appv2.QMessageBox.StandardButton.No))
    w.mint_session()
    assert s.registered == [] and s.adopted == []
    # Debounce path (workbench field find 2026-08-20): a just-minted live key
    # means a repeat press, not a new sitting.
    monkeypatch.setattr(
        appv2.QMessageBox, "question",
        staticmethod(lambda *a, **k: appv2.QMessageBox.StandardButton.Yes))
    w._live_key = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    w.mint_session()
    assert s.registered == []
