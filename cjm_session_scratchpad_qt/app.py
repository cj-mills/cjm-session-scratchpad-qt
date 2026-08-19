"""The scratchpad shell: composition seat v0 (DECs 2a062aff + ea85eab7).

One window, one file. A QPlainTextEdit editor (theme body font + measure,
no line-height merges — undo integrity) and a QTextBrowser rendered view
(the lane's first real exerciser of document_css/heading-scale/measure on
rich text) behind a one-key toggle that holds the reading position in BOTH
directions: the renderer's per-block source-line anchors map top-visible
edit line -> rendered anchor, and rendered top block -> source line. Saving
is autosave-only — debounced idle, plus toggle / focus-loss / close — with
atomic writes and a file-watcher guard (clean buffer follows disk, dirty
buffer banners and holds; no dialogs, ever). Every gesture is a
KeymapRegistry verb, so the table is the discovery surface and new gestures
stay cheap (the accretion tenet)."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from cjm_substrate_qt_kit.findbar import FindBar
from cjm_substrate_qt_kit.keymap import KeymapRegistry
from cjm_substrate_qt_kit.theme import current_theme, make_font, style_text_pane
from PySide6.QtCore import QEvent, QFileSystemWatcher, QPoint, QSettings, QTimer
from PySide6.QtGui import QFontDatabase, QFontMetrics, QTextCursor
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit,
                               QStackedWidget, QStatusBar, QTextBrowser, QVBoxLayout, QWidget)

from .files import atomic_write, ensure_file, SCRATCHPAD_DIR
from .render import nearest_anchor, render_html
from .textops import wrap_selection

AUTOSAVE_MS = 1000


def mono_family(theme: dict) -> str:
    """The rendered code font: the theme's mono token, else the system
    fixed font (the mono token must render well — corpus is code-heavy)."""
    family = str(theme.get("font-mono-family") or "")
    if family:
        return family
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()


def block_line_map(doc) -> List[Tuple[int, int]]:
    """Scan a rendered document for the renderer's Lxx anchors:
    [(block_number, source_line)] ascending — the render->edit half of the
    position mapping."""
    pairs: List[Tuple[int, int]] = []
    block = doc.begin()
    while block.isValid():
        found: Optional[int] = None
        it = block.begin()
        while not it.atEnd() and found is None:
            for name in it.fragment().charFormat().anchorNames():
                if name.startswith("L") and name[1:].isdigit():
                    found = int(name[1:])
                    break
            it += 1
        if found is not None:
            pairs.append((block.blockNumber(), found))
        block = block.next()
    return pairs


class Editor(QPlainTextEdit):
    """The source pane, with line-addressed viewport access for the toggle."""

    def top_line(self) -> int:
        return self.firstVisibleBlock().blockNumber()

    def visible_lines(self) -> int:
        spacing = self.fontMetrics().lineSpacing() or 1
        return max(1, self.viewport().height() // spacing)

    def scroll_to_line(self, line: int) -> None:
        """Put a source line at (approximately) the viewport top; the
        scrollbar counts VISUAL lines, so wrapped blocks are summed."""
        doc = self.document()
        line = max(0, min(line, doc.blockCount() - 1))
        visual = 0
        block = doc.firstBlock()
        for _ in range(line):
            layout = block.layout()
            visual += max(1, layout.lineCount() if layout else 1)
            block = block.next()
        self.verticalScrollBar().setValue(visual)


class ScratchpadWindow(QMainWindow):
    """One session file behind an edit/rendered toggle."""

    def __init__(self, path: Path, banner: Optional[str] = None,
                 directory: Optional[Path] = None):
        super().__init__()
        self.path = Path(path)
        self.directory = directory or SCRATCHPAD_DIR
        self._dirty = False
        self._hold = False
        self._loading = False
        self._bound = False  # no save-before-load until a file is truly bound
        self._anchor_lines: List[int] = []
        self._block_lines: List[Tuple[int, int]] = []

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.editor = Editor()
        editor_row = QWidget()
        row = QHBoxLayout(editor_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(self.editor)
        row.addStretch(1)
        self.editor_container = editor_row
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.editor_container)
        self.stack.addWidget(self.browser)
        self.findbar = FindBar(self.editor)
        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.banner)
        column.addWidget(self.stack, 1)
        column.addWidget(self.findbar)
        self.setCentralWidget(central)

        self.file_label = QLabel()
        self.file_label.setProperty("role", "content-dim")
        self.mode_label = QLabel("EDIT")
        self.save_label = QLabel("")
        self.save_label.setProperty("role", "content-dim")
        bar = QStatusBar()
        bar.addWidget(self.file_label)
        bar.addPermanentWidget(self.mode_label)
        bar.addPermanentWidget(self.save_label)
        self.setStatusBar(bar)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(AUTOSAVE_MS)
        self._save_timer.timeout.connect(self.save_now)
        self.editor.textChanged.connect(self._on_edited)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)

        self.keymap = KeymapRegistry(self)
        self._register_verbs()
        self._build_menus()
        self.refresh_theme()
        app = self._application()
        if app is not None:
            hints = app.styleHints()
            if hasattr(hints, "colorSchemeChanged"):
                hints.colorSchemeChanged.connect(
                    lambda _s: QTimer.singleShot(0, self.refresh_theme))

        self._settings = QSettings("cjm", "cjm-session-scratchpad-qt")
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(980, 760)

        self.bind_path(self.path)
        if banner:
            self.show_banner(banner, role="warn")

    # ----- verbs -------------------------------------------------------

    def _register_verbs(self) -> None:
        add = self.keymap.add
        add("toggle-view", "Toggle edit/rendered view", "Ctrl+/", self.toggle_view)
        add("find", "Find in file", "Ctrl+F", self.open_find)
        add("find-next", "Find next", "F3", self.findbar.next)
        add("find-previous", "Find previous", "Shift+F3", self.findbar.previous)
        add("save-now", "Save now (keeps yours on disk conflict)", "Ctrl+S",
            lambda: self.save_now(force=True))
        add("reload-disk", "Reload from disk (takes disk version)", "Ctrl+Shift+R",
            self.reload_from_disk)
        add("wrap-bold", "Bold selection", "Ctrl+B", lambda: self.wrap("**"))
        add("wrap-italic", "Italic selection", "Ctrl+I", lambda: self.wrap("*"))
        add("wrap-code", "Inline-code selection", "Ctrl+`", lambda: self.wrap("`"))
        add("open-file", "Open file…", "Ctrl+O", self.open_dialog)
        add("quit", "Quit", "Ctrl+Q", self.close)

    def _build_menus(self) -> None:
        menus = {"File": ("open-file", "save-now", "reload-disk", "quit"),
                 "View": ("toggle-view", "find", "find-next", "find-previous"),
                 "Format": ("wrap-bold", "wrap-italic", "wrap-code")}
        for title, verbs in menus.items():
            menu = self.menuBar().addMenu(title)
            for verb in verbs:
                menu.addAction(self.keymap.action(verb))

    # ----- file binding ------------------------------------------------

    def bind_path(self, path: Path) -> None:
        """Bind the window to a file (created blank when new), loading its
        content without waking the autosave. The flush-first only applies to
        a REBOUND window — at construction nothing is loaded yet, and saving
        then would clobber the target with an empty buffer."""
        if self._bound:
            self.save_now()
        self.path = Path(path)
        created = ensure_file(self.path)
        text = self.path.read_text(encoding="utf-8")
        self._loading = True
        try:
            self.editor.setPlainText(text)
        finally:
            self._loading = False
        self._dirty = False
        self._hold = False
        self._bound = True
        self._rewatch()
        self.setWindowTitle(f"{self.path.name} — session scratchpad")
        self.file_label.setText(str(self.path))
        self.save_label.setText("new file" if created else "")
        if self.stack.currentWidget() is self.browser:
            self._to_edit()

    def open_dialog(self) -> None:
        name, _filter = QFileDialog.getOpenFileName(
            self, "Open scratchpad", str(self.directory), "Markdown (*.md);;All files (*)")
        if name:
            self.clear_banner()
            self.bind_path(Path(name))

    # ----- autosave + watcher ------------------------------------------

    def _on_edited(self) -> None:
        if self._loading:
            return
        self._dirty = True
        self._save_timer.start()
        self.save_label.setText("editing…")

    def save_now(self, force: bool = False) -> None:
        """Flush the buffer to disk (atomic). Held after an external change
        until Ctrl+S (force: keep yours) or Ctrl+Shift+R (take disk)."""
        if self._hold and not force:
            return
        if not self._dirty and not force:
            return
        atomic_write(self.path, self.editor.toPlainText())
        self._dirty = False
        self._hold = False
        self._rewatch()
        self.clear_banner()
        self.save_label.setText(f"saved {datetime.now():%H:%M:%S}")

    def reload_from_disk(self) -> None:
        """Take the disk version (the other half of conflict resolution)."""
        try:
            disk = self.path.read_text(encoding="utf-8")
        except OSError:
            return
        top = self.editor.top_line()
        self._loading = True
        try:
            self.editor.setPlainText(disk)
        finally:
            self._loading = False
        self.editor.scroll_to_line(top)
        self._dirty = False
        self._hold = False
        self.clear_banner()
        self.save_label.setText("reloaded from disk")

    def _rewatch(self) -> None:
        """os.replace swaps the inode, which can drop the watch — re-arm."""
        path = str(self.path)
        if self.path.exists() and path not in self.watcher.files():
            self.watcher.addPath(path)

    def _on_file_changed(self, _path: str) -> None:
        self._rewatch()
        try:
            disk = self.path.read_text(encoding="utf-8")
        except OSError:
            return
        if disk == self.editor.toPlainText():
            return  # our own save (or an identical write) — nothing to do
        if not self._dirty:
            self.reload_from_disk()
            self.show_banner("reloaded — file changed on disk", role="info")
        else:
            self._hold = True
            self.show_banner("changed on disk while editing — autosave held · "
                             "Ctrl+S keeps yours · Ctrl+Shift+R takes disk",
                             role="warn")

    # ----- toggle + position mapping -----------------------------------

    def toggle_view(self) -> None:
        if self.stack.currentWidget() is self.editor_container:
            self._to_render()
        else:
            self._to_edit()

    def _to_render(self) -> None:
        self.save_now()
        top = self.editor.top_line()
        theme = current_theme()
        result = render_html(self.editor.toPlainText(), theme, mono_family(theme))
        self._anchor_lines = result.anchor_lines
        self.browser.setHtml(result.html)
        style_text_pane(self.browser, theme, live=True)
        self._block_lines = block_line_map(self.browser.document())
        anchor = nearest_anchor(self._anchor_lines, top)
        if anchor is not None:
            self.browser.scrollToAnchor(f"L{anchor}")
        self.stack.setCurrentWidget(self.browser)
        self.findbar.attach(self.browser)
        self.browser.setFocus()
        self.mode_label.setText("READ")

    def _to_edit(self) -> None:
        cursor = self.browser.cursorForPosition(QPoint(0, 0))
        top_block = cursor.block().blockNumber()
        line = 0
        for block_number, source_line in self._block_lines:
            if block_number > top_block:
                break
            line = source_line
        self.editor.scroll_to_line(line)
        first = self.editor.top_line()
        span = self.editor.visible_lines()
        if not (first <= self.editor.textCursor().blockNumber() <= first + span):
            moved = self.editor.textCursor()
            moved.setPosition(self.editor.document().findBlockByNumber(line).position())
            self.editor.setTextCursor(moved)
        self.stack.setCurrentWidget(self.editor_container)
        self.findbar.attach(self.editor)
        self.editor.setFocus()
        self.mode_label.setText("EDIT")

    # ----- formatting ---------------------------------------------------

    def wrap(self, marker: str) -> None:
        """Apply a wrap-selection operator through one edit block (single
        undo step)."""
        if self.stack.currentWidget() is not self.editor_container:
            return
        cursor = self.editor.textCursor()
        result = wrap_selection(self.editor.toPlainText(),
                                cursor.selectionStart(), cursor.selectionEnd(),
                                marker)
        edit = self.editor.textCursor()
        edit.beginEditBlock()
        edit.setPosition(result.start)
        edit.setPosition(result.end, QTextCursor.MoveMode.KeepAnchor)
        edit.insertText(result.text)
        edit.endEditBlock()
        after = self.editor.textCursor()
        after.setPosition(result.anchor)
        after.setPosition(result.cursor, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(after)

    # ----- find ----------------------------------------------------------

    def open_find(self) -> None:
        pane = (self.browser if self.stack.currentWidget() is self.browser
                else self.editor)
        self.findbar.attach(pane)
        self.findbar.open()

    # ----- banner + theme ------------------------------------------------

    def show_banner(self, text: str, role: str = "warn") -> None:
        self.banner.setProperty("role", role)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.setText("  " + text)
        self.banner.show()

    def clear_banner(self) -> None:
        self.banner.hide()
        self.banner.setText("")

    def refresh_theme(self) -> None:
        """Land typography on both panes: editor gets body font + measure
        width (NO line-height merges — undo integrity), browser gets the
        full reading treatment; a rendered view re-renders for the new
        inline colors."""
        theme = current_theme()
        font = make_font(theme, "body")
        self.editor.setFont(font)
        metrics = QFontMetrics(font)
        was_loading = self._loading
        self._loading = True  # margin change fires textChanged; not a user edit
        try:
            self.editor.document().setDocumentMargin(12.0)
        finally:
            self._loading = was_loading
        width = metrics.averageCharWidth() * int(theme.get("measure") or 68)
        chrome = (2 * int(self.editor.document().documentMargin())
                  + self.editor.verticalScrollBar().sizeHint().width() + 8)
        self.editor.setMaximumWidth(width + chrome)
        self.editor.setTabStopDistance(4 * metrics.horizontalAdvance(" "))
        if self.stack.currentWidget() is self.browser:
            self._to_render()
        else:
            style_text_pane(self.browser, theme, live=True)

    # ----- lifecycle ------------------------------------------------------

    @staticmethod
    def _application():
        from PySide6.QtWidgets import QApplication
        return QApplication.instance()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.save_now()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        self.save_now()
        self._settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)
