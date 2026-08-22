"""The graph-rung scratchpad shell: composition seat v2 (DEC 6e76c120).

One window over the session spine. TOP: the interleaved timeline — one
QTextBrowser document over both chains (transcript messages read-only,
composer parts editable), lane toggle, an independently-scrollable duplicate
lane, superseded transcript branches collapsed behind chips, every affordance
a routed link (copy-id / select / edit / jump / expand). BOTTOM: the
part-composer — an in-flight editing area whose Ctrl+Enter commit gesture
mints the part on-graph and starts the next; compose-send concatenates the
selected committed parts to the clipboard and records a pending-send manifest
that pull-time reconciliation resolves into DERIVED_FROM edges. A QTimer
drives the transcript watcher (sleep-first mtime poll -> in-process pull;
quiet polls journal nothing). Every gesture is a KeymapRegistry verb."""

import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from cjm_substrate_qt_kit.findbar import FindBar
from cjm_substrate_qt_kit.keymap import KeymapRegistry
from cjm_substrate_qt_kit.theme import current_theme, make_font, style_text_pane
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtWidgets import (QApplication, QCompleter, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPlainTextEdit, QSplitter, QStatusBar, QTextBrowser, QVBoxLayout,
                               QWidget)

from .app import mono_family
from .files import atomic_write
from .graph import ScratchpadSession
from .manifest import (compose_text, load_pending, manifest_path, PendingSend, reconcile,
                       save_pending)
from .textops import fence_selection, toggle_list, wrap_selection
from .timeline import build_timeline, TimelineEntry
from .timeline_html import build_timeline_html, LANES
from .watcher import DirWatch

WATCH_MS = 2500      # transcript poll cadence (sleep-first; a tick is one dir scan)
FUTURE_MS = 150      # loop-thread future resolution cadence

# The start-ritual boot prompt the mint gesture puts on the clipboard; its tail
# carries the transcript-mapping signal (prefix-matched by
# cjm_harness_transcripts.mapping.MINT_SIGNAL).
MINT_BOOT_PROMPT = ("Resume. Orient from the resident surface; session rituals "
                    "per the resident notes. New session minted in-scratchpad.")

FENCE_LANGUAGES = ["python", "bash", "json", "yaml", "toml", "markdown", "html",
                   "css", "javascript", "typescript", "sql", "diff", "text",
                   "rust", "c", "cpp", "java", "go"]


class LanguageBar(QWidget):
    """The fence-language mini-bar: a completer-backed field; Enter applies,
    Esc dismisses (671e9b11 pt 6 — fences with language autocomplete)."""

    def __init__(self, apply_fn, parent=None):
        super().__init__(parent)
        self._apply = apply_fn
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        label = QLabel("fence language:")
        label.setProperty("role", "content-dim")
        self.field = QLineEdit(self)
        completer = QCompleter(FENCE_LANGUAGES, self.field)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.field.setCompleter(completer)
        self.field.returnPressed.connect(self._on_return)
        row.addWidget(label)
        row.addWidget(self.field, 1)
        self.hide()

    def open(self) -> None:
        self.show()
        self.field.clear()
        self.field.setFocus()

    def _on_return(self) -> None:
        self.hide()
        self._apply(self.field.text().strip())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)


class SessionPickerDialog(QDialog):
    """The open-session gesture's chooser: filterable Session list, newest
    first, live/open spines annotated; Enter or double-click opens. The graph
    rung's answer to the v1 file rung's open-any-scratchpad."""

    def __init__(self, sessions: List[Dict], current: str, live: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open session")
        self.chosen: Optional[str] = None
        self._sessions = sessions
        self._current = current
        self._live = live
        column = QVBoxLayout(self)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("filter by key or title…")
        self.filter.textChanged.connect(self._refill)
        self.filter.returnPressed.connect(self._choose_current)
        self.listing = QListWidget(self)
        self.listing.itemActivated.connect(self._on_activated)
        column.addWidget(self.filter)
        column.addWidget(self.listing, 1)
        self._refill()
        self.filter.setFocus()
        self.resize(720, 480)

    def _refill(self) -> None:
        needle = self.filter.text().strip().lower()
        self.listing.clear()
        for s in self._sessions:
            label = f"{s['key']}  —  {s['title']}" if s.get("title") else s["key"]
            if needle and needle not in label.lower():
                continue
            marks = [m for m, hit in (("live", s["key"] == self._live),
                                      ("open", s["key"] == self._current)) if hit]
            if marks:
                label += f"   [{' · '.join(marks)}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s["key"])
            self.listing.addItem(item)
        if self.listing.count():
            self.listing.setCurrentRow(0)

    def _choose_current(self) -> None:
        item = self.listing.currentItem()
        if item is not None:
            self._on_activated(item)

    def _on_activated(self, item) -> None:
        self.chosen = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def keyPressEvent(self, event) -> None:
        # Arrow keys steer the list while the filter keeps focus.
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self.listing.keyPressEvent(event)
            return
        super().keyPressEvent(event)


class GraphScratchpadWindow(QMainWindow):
    """One session spine behind a timeline + part-composer."""

    def __init__(self, session: ScratchpadSession, transcript_dir: Path,
                 directory: Path, banner: Optional[str] = None,
                 require_signal: bool = True, live_key: Optional[str] = None):
        super().__init__()
        self.session = session
        self.transcript_dir = Path(transcript_dir)
        self.directory = Path(directory)
        self.require_signal = require_signal
        # The LIVE sitting's key: the watcher only spends pulls on it, and
        # browsing another spine never re-stamps journal attribution.
        self._live_key = live_key or session.session_key
        self._entries: List[TimelineEntry] = []
        self._raw = False
        self._lane = "all"
        self._selected: List[str] = []   # part uuids, selection (= send) order
        self._expanded: Set[int] = set()
        self._editing: Optional[str] = None
        self._stash = ""  # in-flight draft held across an edit-mode detour (drive call-out 2026-08-21)
        self._last_part_uuid: Optional[str] = None
        self._pull_future = None
        self._timeline_future = None
        self._timeline_dirty = False
        self._watch = DirWatch(self.transcript_dir)
        self._manifest_path = manifest_path(self.directory, session.session_key)
        self._pending: List[PendingSend] = load_pending(self._manifest_path)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_link)
        self.dup_browser = QTextBrowser()
        self.dup_browser.setOpenLinks(False)
        self.dup_browser.anchorClicked.connect(self._on_link)
        self.dup_browser.hide()
        self.lanes = QSplitter(Qt.Orientation.Horizontal)
        self.lanes.addWidget(self.browser)
        self.lanes.addWidget(self.dup_browser)
        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText(
            "compose a part… Ctrl+Enter commits it to the graph")
        self.langbar = LanguageBar(self._apply_fence)
        composer_box = QWidget()
        column = QVBoxLayout(composer_box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.composer)
        column.addWidget(self.langbar)
        self.split = QSplitter(Qt.Orientation.Vertical)
        self.split.addWidget(self.lanes)
        self.split.addWidget(composer_box)
        self.split.setStretchFactor(0, 4)
        self.split.setStretchFactor(1, 1)
        self.findbar = FindBar(self.browser)
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.banner)
        outer.addWidget(self.split, 1)
        outer.addWidget(self.findbar)
        self.setCentralWidget(central)

        self.key_label = QLabel(session.session_key)
        self.key_label.setProperty("role", "content-dim")
        self.count_label = QLabel("")
        self.count_label.setProperty("role", "content-dim")
        self.pull_label = QLabel("watching…" if self.is_live else
                                 "browsing — F5 pulls if a transcript remains")
        self.pull_label.setProperty("role", "content-dim")
        self.mode_label = QLabel("RENDERED · all")
        bar = QStatusBar()
        bar.addWidget(self.key_label)
        bar.addWidget(self.count_label)
        bar.addPermanentWidget(self.pull_label)
        bar.addPermanentWidget(self.mode_label)
        self.setStatusBar(bar)

        self.keymap = KeymapRegistry(self)
        self._register_verbs()
        self._build_menus()
        self.refresh_theme()
        app = QApplication.instance()
        if app is not None:
            hints = app.styleHints()
            if hasattr(hints, "colorSchemeChanged"):
                hints.colorSchemeChanged.connect(
                    lambda _s: QTimer.singleShot(0, self.refresh_theme))

        self._settings = QSettings("cjm", "cjm-session-scratchpad-qt")
        geometry = self._settings.value("geometry-v2")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1080, 820)
        self.setWindowTitle(f"{session.session_key} — session scratchpad (graph)")
        if banner:
            self.show_banner(banner, role="warn")

        self._future_timer = QTimer(self)
        self._future_timer.setInterval(FUTURE_MS)
        self._future_timer.timeout.connect(self._resolve_futures)
        self._future_timer.start()
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(WATCH_MS)
        self._watch_timer.timeout.connect(self._on_watch_tick)
        self._watch_timer.start()

        self._load_initial()

    # ----- verbs -------------------------------------------------------

    def _register_verbs(self) -> None:
        add = self.keymap.add
        add("commit-part", "Commit part (mint on-graph)", "Ctrl+Return", self.commit_part)
        add("compose-send", "Compose-send selected parts → clipboard", "Ctrl+Shift+Return",
            self.compose_send)
        add("pull-now", "Pull transcript now (backfill gesture)", "F5", self.pull_now)
        add("open-session", "Open session… (any spine on this graph)", "Ctrl+O",
            self.open_session_picker)
        add("mint-session", "Mint new session (start ritual)", "Ctrl+Shift+N",
            self.mint_session)
        add("export-md", "Export session → .md (one projection among N)", "Ctrl+E",
            self.export_md)
        add("toggle-raw", "Toggle raw/rendered timeline", "Ctrl+/", self.toggle_raw)
        add("cycle-lane", "Cycle timeline lane (all/composition/transcript)", "Ctrl+L",
            self.cycle_lane)
        add("toggle-dup-lane", "Toggle duplicate timeline lane", "Ctrl+D", self.toggle_dup)
        add("find", "Find in timeline/composer", "Ctrl+F", self.open_find)
        add("find-next", "Find next", "F3", self.findbar.next)
        add("find-previous", "Find previous", "Shift+F3", self.findbar.previous)
        add("wrap-bold", "Bold selection", "Ctrl+B", lambda: self.wrap("**"))
        add("wrap-italic", "Italic selection", "Ctrl+I", lambda: self.wrap("*"))
        add("wrap-code", "Inline-code selection", "Ctrl+`", lambda: self.wrap("`"))
        add("fence", "Code fence (language autocomplete)", "Ctrl+Shift+K",
            self.langbar.open)
        add("list-unordered", "Toggle bullet list", "Ctrl+Shift+8",
            lambda: self._apply_block(toggle_list, ordered=False))
        add("list-ordered", "Toggle numbered list", "Ctrl+Shift+7",
            lambda: self._apply_block(toggle_list, ordered=True))
        add("cancel-edit", "Cancel part edit", "Ctrl+Shift+X", self.cancel_edit)
        add("quit", "Quit", "Ctrl+Q", self.close)

    def _build_menus(self) -> None:
        menus = {"File": ("mint-session", "open-session", "pull-now", "export-md",
                          "quit"),
                 "View": ("toggle-raw", "cycle-lane", "toggle-dup-lane", "find",
                          "find-next", "find-previous"),
                 "Format": ("wrap-bold", "wrap-italic", "wrap-code", "fence",
                            "list-unordered", "list-ordered"),
                 "Compose": ("commit-part", "compose-send", "cancel-edit")}
        for title, verbs in menus.items():
            menu = self.menuBar().addMenu(title)
            for verb in verbs:
                menu.addAction(self.keymap.action(verb))

    # ----- initial load + reconciliation --------------------------------

    def _load_initial(self) -> None:
        messages, next_pairs, derived_pairs = self.session.timeline_data()
        self._entries = build_timeline(messages, next_pairs, derived_pairs)
        self._sync_part_tail()
        self._render_timeline()
        # A send recorded in an earlier run may already be on the graph.
        self._reconcile([{"source_uuid": e.source_uuid, "text": e.text}
                         for e in self._entries
                         if e.source != "composer" and e.role == "user"])

    def _sync_part_tail(self) -> None:
        parts = [e for e in self._entries if e.source == "composer"]
        if parts and self._last_part_uuid is None:
            self._last_part_uuid = parts[-1].source_uuid

    def _reconcile(self, user_messages: List[Dict]) -> None:
        """Resolve pending-send manifests against pulled user messages: exact
        matches mint DERIVED_FROM (journaled); the rest stay pending."""
        if not self._pending or not user_messages:
            return
        derivations, remaining = reconcile(self._pending, user_messages)
        for sent_uuid, part_uuids in derivations:
            self.session.record_send(sent_uuid, part_uuids)
        if derivations:
            self._pending = remaining
            save_pending(self._manifest_path, self._pending)
            self.show_status(f"compose-send reconciled: {len(derivations)} send(s) derived")
            self.request_timeline()

    # ----- watcher + futures ---------------------------------------------

    @property
    def is_live(self) -> bool:
        """Viewing the live sitting's spine? (Watcher + label gate.)"""
        return self.session.session_key == self._live_key

    def _on_watch_tick(self) -> None:
        if not self.is_live:
            return  # a past spine's transcript never grows; F5 stays available
        if self._pull_future is None and self._watch.changed():
            self._pull_future = self.session.pull_async(
                str(self.transcript_dir), require_signal=self.require_signal)

    def _resolve_futures(self) -> None:
        if self._pull_future is not None and self._pull_future.done():
            future, self._pull_future = self._pull_future, None
            try:
                res = future.result()
            except Exception as exc:  # surfaced, never swallowed
                self.pull_label.setText(f"pull failed: {exc}")
                return
            self._on_pull_result(res)
        if self._timeline_future is not None and self._timeline_future.done():
            future, self._timeline_future = self._timeline_future, None
            try:
                data = future.result()
            except Exception as exc:
                self.show_status(f"timeline read failed: {exc}")
                return
            self._entries = build_timeline(*data)
            self._sync_part_tail()
            self._render_timeline()
            if self._timeline_dirty:
                self._timeline_dirty = False
                self.request_timeline()

    def _on_pull_result(self, res: Dict) -> None:
        if res.get("error"):
            self.pull_label.setText(str(res["error"])[:80])
            return
        new = int(res.get("messages_new") or 0)
        self.pull_label.setText(
            f"pulled {new} new / {res.get('messages_total', 0)} total")
        if new:
            self.request_timeline()
            self._reconcile([m | {"source_uuid": m["uuid"]}
                             for m in res.get("new_messages") or []
                             if m.get("role") == "user"])

    def request_timeline(self) -> None:
        """Async timeline refresh (the paint thread never blocks on a read)."""
        if self._timeline_future is not None:
            self._timeline_dirty = True
            return
        self._timeline_future = self.session.timeline_data_async()

    # ----- rendering ------------------------------------------------------

    def _render_timeline(self) -> None:
        theme = current_theme()
        html = build_timeline_html(
            self._entries, theme, mono_family(theme), lane=self._lane,
            raw=self._raw, selected=self._selected, editing=self._editing,
            expanded=self._expanded)
        for pane in (self.browser, self.dup_browser):
            pos = pane.verticalScrollBar().value()
            pane.setHtml(html)
            pane.verticalScrollBar().setValue(pos)
        transcript = sum(1 for e in self._entries if e.source != "composer")
        parts = len(self._entries) - transcript
        sel = f" · {len(self._selected)} selected" if self._selected else ""
        self.count_label.setText(f"  {transcript} transcript · {parts} part(s){sel}")
        self.mode_label.setText(f"{'RAW' if self._raw else 'RENDERED'} · {self._lane}"
                                + (f" · editing {self._editing[:8]}" if self._editing else ""))

    # ----- link routing ----------------------------------------------------

    def _on_link(self, url: QUrl) -> None:
        scheme, ref = url.scheme(), url.toString().split("://", 1)[-1]
        if scheme == "copy":
            QApplication.clipboard().setText(ref)
            self.show_status(f"copied node id {ref[:8]}…")
        elif scheme == "sel":
            if ref in self._selected:
                self._selected.remove(ref)
            else:
                self._selected.append(ref)
            self._render_timeline()
        elif scheme == "edit":
            self.start_edit(ref)
        elif scheme == "branch":
            index = int(ref)
            self._expanded.symmetric_difference_update({index})
            self._render_timeline()
        elif scheme == "jump":
            self.browser.scrollToAnchor(f"m-{ref}")

    # ----- composer verbs ---------------------------------------------------

    def commit_part(self) -> None:
        """Ctrl+Enter: mint the in-flight text as a part (or land an edit)."""
        text = self.composer.toPlainText().strip()
        if not text:
            return
        if self._editing:
            res = self.session.edit_part(self._editing, text)
            if res.get("error"):
                self.show_banner(str(res["error"]), role="warn")
                return
            self.show_status(f"part {self._editing[:8]} edited (journaled)")
            self._editing = None
            self._restore_stash()
        else:
            res = self.session.commit_part(text, prev_uuid=self._last_part_uuid)
            if res.get("error"):
                self.show_banner(str(res["error"]), role="warn")
                return
            self._last_part_uuid = res["payload"]["uuid"]
            self.show_status(f"part committed → {res['payload']['uuid'][:8]}")
            self.composer.clear()
        self.request_timeline()

    def start_edit(self, part_uuid: str) -> None:
        entry = next((e for e in self._entries if e.source_uuid == part_uuid
                      and e.editable), None)
        if entry is None:
            return
        if self._editing is None:
            # An edit click must never eat the in-flight draft (drive call-out
            # 2026-08-21) — stash it, restore when the edit lands or cancels.
            self._stash = self.composer.toPlainText()
        self._editing = part_uuid
        self.composer.setPlainText(entry.text)
        self.composer.setFocus()
        self._render_timeline()

    def cancel_edit(self) -> None:
        if self._editing is None:
            return
        self._editing = None
        self._restore_stash()
        self._render_timeline()

    def _restore_stash(self) -> None:
        """Hand the held draft back to the composer (caret at the end)."""
        self.composer.setPlainText(self._stash)
        self._stash = ""
        cursor = self.composer.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.composer.setTextCursor(cursor)

    def compose_send(self) -> None:
        """Concatenate the selected parts → clipboard + pending-send manifest
        (clipboard stays the transport — zero harness integration)."""
        by_uuid = {e.source_uuid: e for e in self._entries if e.editable}
        chosen = [by_uuid[u] for u in self._selected if u in by_uuid]
        if not chosen:
            self.show_status("compose-send: no parts selected (☐ select on part cards)")
            return
        text = compose_text([e.text for e in chosen])
        QApplication.clipboard().setText(text)
        self._pending.append(PendingSend(part_uuids=[e.source_uuid for e in chosen],
                                         text=text))
        save_pending(self._manifest_path, self._pending)
        self.show_status(f"compose-send: {len(chosen)} part(s) → clipboard; "
                         f"manifest recorded, reconciles at pull")
        self._selected = []
        self._render_timeline()

    def mint_session(self) -> None:
        """Ctrl+Shift+N: mint + register a new session spine, point
        .cjm/current-session at it, adopt it, and put the boot prompt on the
        clipboard — the workbench Shift+S start ritual, scratchpad-shaped."""
        try:
            # Key-repeat/double-tap debounce (workbench field find 2026-08-20):
            # a just-minted live key means this press is a repeat, not a sitting.
            age = time.time() - datetime.strptime(
                self._live_key, "%Y-%m-%d_%H-%M-%S").timestamp()
            if 0 <= age < 10.0:
                self.show_status(f"session {self._live_key} just minted — ignored")
                return
        except ValueError:
            pass  # non-timestamp live key (manual/legacy) — no debounce basis
        key = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        confirm = QMessageBox.question(
            self, "Mint new session",
            f"Mint session {key} and adopt it as the live sitting?\n\n"
            f"The .cjm/current-session pointer moves and the boot prompt "
            f"lands on the clipboard.")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        prev_live = self._live_key
        # Adopt BEFORE the journaled write: the registration op must stamp to
        # its OWN session, never the outgoing one (S-test find 2026-08-14).
        self.rebind_spine(key, adopt=True)
        res = self.session.register_session(key, started_at=time.time())
        if res.get("error"):
            self.rebind_spine(prev_live, adopt=True)
            self.show_banner(f"session mint failed: {res['error']}", role="warn")
            return
        pointer = self.session.write_session_pointer(key)
        QApplication.clipboard().setText(MINT_BOOT_PROMPT)
        self.show_status(
            f"session {key} minted + adopted — boot prompt on clipboard"
            + ("" if pointer else " · ⚠ no journal: pointer NOT written"))

    def open_session_picker(self) -> None:
        """Ctrl+O: choose any Session spine on the graph (recent first)."""
        try:
            sessions = self.session.list_sessions()
        except Exception as exc:  # surfaced, never swallowed
            self.show_banner(f"session list failed: {exc}", role="warn")
            return
        dialog = SessionPickerDialog(sessions, current=self.session.session_key,
                                     live=self._live_key, parent=self)
        if dialog.exec() and dialog.chosen:
            self.rebind_spine(dialog.chosen)

    def rebind_spine(self, key: str, *, adopt: bool = False) -> None:
        """Swap the seat onto another Session spine: per-spine view state
        resets, the pending-send manifest follows the key, the watcher gates
        itself on is_live (journal attribution stays with the live sitting —
        composing onto a past spine is legitimate retro authoring). adopt=True
        (the mint gesture) makes the target the LIVE spine: CJM_SESSION
        re-stamps and the watcher follows."""
        if key == self.session.session_key and not adopt:
            return
        if self._editing:
            self.cancel_edit()   # the stash hands any in-flight draft back
        self._selected = []
        self._expanded = set()
        self._last_part_uuid = None
        self._pull_future = None      # an in-flight pull's result is stale now
        self._timeline_future = None
        self._timeline_dirty = False
        self.session.rebind(key, adopt=adopt)
        if adopt:
            self._live_key = key
        self._manifest_path = manifest_path(self.directory, key)
        self._pending = load_pending(self._manifest_path)
        self.key_label.setText(key + ("" if self.is_live else "  (past)"))
        self.setWindowTitle(f"{key} — session scratchpad (graph)")
        self.pull_label.setText("watching…" if self.is_live else
                                "browsing — F5 pulls if a transcript remains")
        self._load_initial()
        self.show_status(f"opened session {key}" + ("" if self.is_live else
                         " — past spine: composer live, watcher off"))

    def pull_now(self) -> None:
        """The backfill gesture (watcher stays primary)."""
        if self._pull_future is None:
            self.pull_label.setText("pulling…")
            self._pull_future = self.session.pull_async(
                str(self.transcript_dir), require_signal=self.require_signal)

    def export_md(self) -> None:
        """The exporter lens (5ab24c57): write the session's .md projection
        next to the file-rung scratchpads. One-way — an edited export is a
        fork, never a sync."""
        res = self.session.export_markdown()
        if res.get("error"):
            self.show_banner(str(res["error"]), role="warn")
            return
        path = self.directory / f"{self.session.session_key}.export.md"
        atomic_write(path, res["text"])
        self.show_status(f"exported {res['messages']} message(s) + "
                         f"{res['parts']} part(s) → {path}")

    # ----- formatting ---------------------------------------------------

    def wrap(self, marker: str) -> None:
        self._apply_block(wrap_selection, marker)

    def _apply_fence(self, language: str) -> None:
        self._apply_block(fence_selection, language)
        self.composer.setFocus()

    def _apply_block(self, op, *args, **kwargs) -> None:
        """Run a pure textop over the composer selection through one edit
        block (single undo step)."""
        cursor = self.composer.textCursor()
        result = op(self.composer.toPlainText(), cursor.selectionStart(),
                    cursor.selectionEnd(), *args, **kwargs)
        edit = self.composer.textCursor()
        edit.beginEditBlock()
        edit.setPosition(result.start)
        edit.setPosition(result.end, QTextCursor.MoveMode.KeepAnchor)
        edit.insertText(result.text)
        edit.endEditBlock()
        after = self.composer.textCursor()
        after.setPosition(result.anchor)
        after.setPosition(result.cursor, QTextCursor.MoveMode.KeepAnchor)
        self.composer.setTextCursor(after)

    # ----- view toggles ---------------------------------------------------

    def toggle_raw(self) -> None:
        self._raw = not self._raw
        self._render_timeline()

    def cycle_lane(self) -> None:
        self._lane = LANES[(LANES.index(self._lane) + 1) % len(LANES)]
        self._render_timeline()

    def toggle_dup(self) -> None:
        """The independently-navigable duplicate lane (671e9b11 pt 1): same
        document, its own scrollbar — earlier context stays on-screen."""
        self.dup_browser.setVisible(not self.dup_browser.isVisible())

    def open_find(self) -> None:
        pane = self.composer if self.composer.hasFocus() else self.browser
        self.findbar.attach(pane)
        self.findbar.open()

    # ----- banner + status + theme ----------------------------------------

    def show_banner(self, text: str, role: str = "warn") -> None:
        self.banner.setProperty("role", role)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.setText("  " + text)
        self.banner.show()

    def show_status(self, text: str) -> None:
        self.statusBar().showMessage(text, 6000)

    def refresh_theme(self) -> None:
        theme = current_theme()
        font = make_font(theme, "body")
        self.composer.setFont(font)
        metrics = QFontMetrics(font)
        self.composer.setTabStopDistance(4 * metrics.horizontalAdvance(" "))
        self.composer.document().setDocumentMargin(10.0)
        for pane in (self.browser, self.dup_browser):
            style_text_pane(pane, theme, live=True)
        self._render_timeline()

    # ----- lifecycle ------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._settings.setValue("geometry-v2", self.saveGeometry())
        super().closeEvent(event)
