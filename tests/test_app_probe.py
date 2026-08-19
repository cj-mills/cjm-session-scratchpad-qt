"""Shell probe (offscreen): bind/birth, autosave flush + atomicity, the
position-stable toggle round trip, wrap verbs through the registry, the
external-change guard's two branches, and the verb table."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from cjm_session_scratchpad_qt.app import ScratchpadWindow, block_line_map

MD = "\n\n".join(f"## Section {i}\n\nparagraph {i} with `code_{i}` inline"
                 for i in range(30))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make(app, tmp_path, text=MD, name="2026-08-19_10-55-10.md"):
    path = tmp_path / name
    if text is not None:
        path.write_text(text)
    return ScratchpadWindow(path, directory=tmp_path)


def test_bind_births_blank_file(app, tmp_path):
    w = make(app, tmp_path, text=None)
    assert w.path.exists() and w.path.read_text() == ""
    assert w.save_label.text() == "new file"


def test_autosave_flushes_edits(app, tmp_path):
    w = make(app, tmp_path, text="start")
    w.editor.setPlainText("start edited")
    assert w._dirty and w._save_timer.isActive()
    w.save_now()
    assert w.path.read_text() == "start edited"
    assert not w._dirty


def test_toggle_renders_and_maps_positions(app, tmp_path):
    w = make(app, tmp_path)
    w.resize(900, 600)
    w.show()
    app.processEvents()
    w.editor.scroll_to_line(60)
    top_before = w.editor.top_line()
    assert top_before > 0
    w.toggle_view()
    assert w.stack.currentWidget() is w.browser
    assert w.mode_label.text() == "READ"
    assert block_line_map(w.browser.document())  # anchors survived setHtml
    assert w.browser.verticalScrollBar().value() > 0  # position carried over
    w.toggle_view()
    assert w.stack.currentWidget() is w.editor_container
    assert abs(w.editor.top_line() - top_before) <= 3  # round trip holds
    w.close()


def test_toggle_saves_first(app, tmp_path):
    w = make(app, tmp_path, text="v1")
    w.editor.setPlainText("v2 unsaved")
    w.toggle_view()
    assert w.path.read_text() == "v2 unsaved"


def test_wrap_verb_via_registry(app, tmp_path):
    w = make(app, tmp_path, text="make bold now")
    cursor = w.editor.textCursor()
    cursor.setPosition(5)
    cursor.setPosition(9, cursor.MoveMode.KeepAnchor)
    w.editor.setTextCursor(cursor)
    w.keymap.action("wrap-bold").trigger()
    assert w.editor.toPlainText() == "make **bold** now"
    w.keymap.action("wrap-bold").trigger()  # toggles back off
    assert w.editor.toPlainText() == "make bold now"


def test_external_change_clean_buffer_reloads(app, tmp_path):
    w = make(app, tmp_path, text="v1")
    w.path.write_text("external v2")
    w._on_file_changed(str(w.path))
    assert w.editor.toPlainText() == "external v2"
    assert not w.banner.isHidden()


def test_external_change_dirty_buffer_holds(app, tmp_path):
    w = make(app, tmp_path, text="v1")
    w.editor.setPlainText("mine v2")
    w.path.write_text("theirs v2")
    w._on_file_changed(str(w.path))
    assert w._hold
    assert "autosave held" in w.banner.text()
    w.save_now()  # held: plain autosave must NOT clobber
    assert w.path.read_text() == "theirs v2"
    w.save_now(force=True)  # Ctrl+S keeps yours
    assert w.path.read_text() == "mine v2"
    assert not w._hold


def test_external_change_in_read_view_rerenders(app, tmp_path):
    w = make(app, tmp_path, text="# old headline")
    w.toggle_view()
    assert "old headline" in w.browser.toPlainText()
    w.path.write_text("# new headline")
    w._on_file_changed(str(w.path))
    assert w.stack.currentWidget() is w.browser
    assert "new headline" in w.browser.toPlainText()


def test_reload_from_disk_takes_disk(app, tmp_path):
    w = make(app, tmp_path, text="v1")
    w.editor.setPlainText("mine")
    w.path.write_text("disk wins")
    w.reload_from_disk()
    assert w.editor.toPlainText() == "disk wins"
    assert not w._dirty


def test_verb_table_is_discoverable(app, tmp_path):
    w = make(app, tmp_path, text="x")
    verbs = {e["verb"]: e["key"] for e in w.keymap.entries()}
    assert verbs["toggle-view"] == "Ctrl+/"
    assert verbs["find"] == "Ctrl+F"
    assert verbs["wrap-bold"] == "Ctrl+B"
    assert verbs["quit"] == "Ctrl+Q"
