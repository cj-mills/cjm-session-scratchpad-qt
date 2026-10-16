"""THE SEAT'S WRITE ORDER (ruling d2d05e78 (4), work item eeda5977 leg L4): the scratchpad's write
gestures run the CLI's own landing functions inside its unit of work, held to the CLI's proof --
- every gesture's ops land in the writes journal, a gesture that changes nothing journals nothing
  (a quiet pull leaves no trace), and the db's applied cursor stands at the journal's end;
- the live db equals the replay of its journal ELEMENT FOR ELEMENT (`rebuild-diff`, ruling f8b9c728)
  -- a pull's re-linked messages ride its op (finding F2: the app's pull once landed them unjournaled);
- a pull killed between its append and its apply (CJM_JOURNAL_FAULT, exit 86) heals at the next
  pull's writer, which then plans nothing, so the journal equals the uncrashed run's.
Drives the real projection CLI (replay, rebuild-diff, journal-cursor) beside the session."""

import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil
import pytest
from cjm_context_graph_primitives.journal import read_journal
from cjm_context_graph_primitives.writer import FAULT_EXIT, JOURNAL_FAULT_ENV
from cjm_context_graph_projection.runtime import DEFAULT_GRAPH_ID, DEFAULT_MANIFESTS
from cjm_session_scratchpad_qt.graph import ScratchpadSession

pytestmark = pytest.mark.skipif(
    not (Path(DEFAULT_MANIFESTS) / f"{DEFAULT_GRAPH_ID}.json").exists(),
    reason=f"graph capability {DEFAULT_GRAPH_ID!r} not installed at {DEFAULT_MANIFESTS}",
)

KEY = "2026-01-01_00-00-00"
# A harness transcript booted just after KEY's mint (the key is LOCAL time, a record's stamp UTC)
BOOT = (datetime.strptime(KEY, "%Y-%m-%d_%H-%M-%S").astimezone() + timedelta(seconds=5)).astimezone(timezone.utc)


def _record(uuid: str, parent, role: str, text: str, after_s: int) -> dict:
    content = text if role == "user" else [{"type": "text", "text": text}]
    return {"type": role, "isSidechain": False, "uuid": uuid, "parentUuid": parent,
            "timestamp": (BOOT + timedelta(seconds=after_s)).isoformat().replace("+00:00", "Z"),
            "message": {"role": role, "content": content}}


BOOT_MSG = _record("u-boot", None, "user", "Resume. New session minted in-scratchpad.", 0)
REPLY = _record("u-reply", "u-boot", "assistant", "On it.", 4)
MID = _record("u-mid", "u-boot", "assistant", "Reading the surface.", 2)


def _transcript(run: Path, *records: dict) -> Path:
    d = run / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    (d / "aaaa1111-2222-3333-4444-555566667777.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    return d


def _cli(db: Path, jp: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "cjm_context_graph_projection.cli",
                           "--graph-db-path", str(db), "--journal-path", str(jp), *args],
                          capture_output=True, text=True)


def _graph(run: Path) -> tuple:  # (db, writes journal): a graph whose spine is registered through the CLI
    run.mkdir(parents=True, exist_ok=True)
    (run / "graph.config.json").write_text(json.dumps({"memory_journal_path": str(run / "memory.jsonl")}))
    db, jp = run / "live.db", run / "writes.jsonl"
    r = _cli(db, jp, "session", KEY)
    assert r.returncode == 0, r.stderr
    return db, jp


def _ops(jp: Path) -> list:  # The journal as (verb, args): the clock abstracted
    return [(o["verb"], o["args"]) for o in read_journal(str(jp))]


def _held(db: Path, jp: Path) -> None:  # The cursor at the journal's end, the live db its replay
    r = _cli(db, jp, "journal-cursor")
    assert r.returncode == 0, f"the db's cursor is behind its journal: {r.stdout}{r.stderr}"
    rebuilt = db.parent / "rebuilt.db"
    r = _cli(rebuilt, jp, "replay")
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, "-m", "cjm_context_graph_projection.cli", "--graph-db-path", str(db),
                        "rebuild-diff", "--against", str(rebuilt)], capture_output=True, text=True)
    assert r.returncode == 0, f"live != its replay:\n{r.stdout}{r.stderr}"


def _pull(db: Path, jp: Path, transcripts: Path, crash: int = 0) -> subprocess.CompletedProcess:
    """One pull gesture in a process of its own -- armed, it dies between its op's append and apply."""
    code = textwrap.dedent(f"""
        from cjm_session_scratchpad_qt.graph import ScratchpadSession
        s = ScratchpadSession({str(db)!r}, {KEY!r}, journal_paths=[{str(jp)!r}])
        s.start()
        res = s.pull({str(transcripts)!r})
        assert not res.get("error"), res
        s.close()
    """)
    env = {**os.environ, **({JOURNAL_FAULT_ENV: f"after_append@{crash}"} if crash else {})}
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env)
    out, err = proc.communicate()
    if crash:  # the crashed host's capability worker outlives it (finding f1734c73)
        for p in psutil.process_iter(["cmdline"]):
            cmd = p.info["cmdline"] or []
            if "--ppid" in cmd and cmd[cmd.index("--ppid") + 1:cmd.index("--ppid") + 2] == [str(proc.pid)]:
                p.terminate()
                p.wait(10)
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def test_every_write_gesture_lands_journaled_and_live_is_its_replay(tmp_path):
    db, jp = _graph(tmp_path)
    transcripts = _transcript(tmp_path, BOOT_MSG, REPLY)
    s = ScratchpadSession(str(db), KEY, journal_paths=[str(jp)])
    s.start()
    try:
        def step(fn, *verbs):
            before = len(_ops(jp))
            res = fn()
            assert not res.get("error"), res
            assert [v for v, _ in _ops(jp)[before:]] == list(verbs), (verbs, res)
            return res

        step(lambda: s.register_session(KEY, started_at=1.0), "session")
        p1 = step(lambda: s.commit_part("part one"), "mint-messages")["payload"]["uuid"]
        p2 = step(lambda: s.commit_part("part two", prev_uuid=p1), "mint-messages")["payload"]["uuid"]
        step(lambda: s.edit_part(p1, "part one, edited"), "edit-message")
        step(lambda: s.edit_part(p1, "part one, edited"))                         # no change
        assert step(lambda: s.pull(str(transcripts)), "pull-transcript")["messages_new"] == 2
        step(lambda: s.pull(str(transcripts)))                                    # a quiet pull: no trace
        step(lambda: s.record_send("u-boot", [p1, p2]), "derive-message")
        step(lambda: s.record_send("u-boot", [p1, p2]))                           # no change
        # a wider extraction yields a message BETWEEN the boot and the reply: the reply rides the op
        # with it, the stale boot -> reply NEXT edge is the planned unlink after it
        _transcript(tmp_path, BOOT_MSG, MID, {**REPLY, "parentUuid": "u-mid"})
        step(lambda: s.pull(str(transcripts)), "pull-transcript", "unlink")
        assert [m["uuid"] for m in _ops(jp)[-2][1]["messages"]] == ["u-mid", "u-reply"]
        refused = s.record_send("u-sent-never-pulled", [p1])
        assert "no Message node" in refused["error"]
    finally:
        s.close()
    _held(db, jp)


def test_a_crashed_pull_heals_at_the_next_pull(tmp_path):
    a = tmp_path / "a"
    uncrashed_db, uncrashed_jp = _graph(a)
    assert _pull(uncrashed_db, uncrashed_jp, _transcript(a, BOOT_MSG, REPLY)).returncode == 0
    b = tmp_path / "b"
    db, jp = _graph(b)
    transcripts = _transcript(b, BOOT_MSG, REPLY)
    r = _pull(db, jp, transcripts, crash=1)
    assert r.returncode == FAULT_EXIT, f"no crash ({r.returncode}): {r.stderr}"
    assert "1 record(s) past it" in _cli(db, jp, "journal-cursor").stdout
    assert _pull(db, jp, transcripts).returncode == 0      # heals the pull op, then plans nothing
    assert json.loads(json.dumps(_ops(jp)).replace(str(b), "{run}")) == \
        json.loads(json.dumps(_ops(uncrashed_jp)).replace(str(a), "{run}"))
    _held(db, jp)
