"""Launch contract: pointer walk-up, blank birth, absent/stale banners,
atomic writes."""

from datetime import date

from cjm_session_scratchpad_qt.files import (atomic_write, ensure_file,
                                             find_session_key, most_recent,
                                             parse_key_time, resolve_target)

KEY = "2026-08-19_10-55-10"


def make_pointer(root, key=KEY):
    (root / ".cjm").mkdir(parents=True, exist_ok=True)
    (root / ".cjm" / "current-session").write_text(key + "\n")


def test_pointer_resolves_walking_up(tmp_path):
    make_pointer(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_session_key(nested) == KEY


def test_no_pointer_returns_none(tmp_path):
    assert find_session_key(tmp_path) is None


def test_parse_key_time():
    assert parse_key_time(KEY).hour == 10
    assert parse_key_time("cc-scratchpad-old") is None


def test_resolve_prefers_explicit_path(tmp_path):
    make_pointer(tmp_path)
    t = resolve_target(tmp_path, arg="/somewhere/else.md", directory=tmp_path)
    assert str(t.path) == "/somewhere/else.md"
    assert t.banner is None


def test_resolve_session_key_same_day_no_banner(tmp_path):
    make_pointer(tmp_path)
    t = resolve_target(tmp_path, directory=tmp_path, today=date(2026, 8, 19))
    assert t.path == tmp_path / f"{KEY}.md"
    assert t.banner is None


def test_resolve_stale_key_banners(tmp_path):
    make_pointer(tmp_path)
    t = resolve_target(tmp_path, directory=tmp_path, today=date(2026, 8, 20))
    assert t.path == tmp_path / f"{KEY}.md"
    assert "stale" in t.banner


def test_absent_pointer_opens_most_recent_with_banner(tmp_path):
    old = tmp_path / "2026-08-01_09-00-00.md"
    new = tmp_path / "2026-08-15_09-00-00.md"
    old.write_text("old")
    new.write_text("new")
    t = resolve_target(tmp_path, directory=tmp_path)
    assert t.path == new
    assert "most recent" in t.banner


def test_absent_pointer_empty_dir_untitled(tmp_path):
    t = resolve_target(tmp_path, directory=tmp_path)
    assert t.path.name == "untitled.md"
    assert "no .cjm/current-session" in t.banner


def test_most_recent_ignores_non_markdown(tmp_path):
    (tmp_path / "x.txt").write_text("x")
    assert most_recent(tmp_path) is None


def test_ensure_file_births_blank_once(tmp_path):
    path = tmp_path / "sub" / "s.md"
    assert ensure_file(path) is True
    assert path.read_text() == ""
    assert ensure_file(path) is False


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path):
    path = tmp_path / "s.md"
    path.write_text("v1")
    atomic_write(path, "v2")
    assert path.read_text() == "v2"
    assert [p.name for p in tmp_path.iterdir()] == ["s.md"]
