"""Timeline derivation: interleave, active-path walk, birth-class flags,
superseded-run grouping."""

from cjm_session_scratchpad_qt.timeline import build_timeline, timeline_blocks


def msg(nid, uuid, ts, role="user", source="cc-transcript", text="t"):
    return {"id": nid, "source_uuid": uuid, "role": role, "text": text,
            "timestamp": ts, "source": source}


def test_interleaves_chronologically_across_chains():
    messages = [
        msg("n1", "u1", "2026-08-21T10:00:00.000Z"),
        msg("p1", "c1", "2026-08-21T10:00:30.000Z", source="composer"),
        msg("n2", "a1", "2026-08-21T10:01:00.000Z", role="assistant"),
    ]
    entries = build_timeline(messages, [("n1", "n2")], [])
    assert [e.node_id for e in entries] == ["n1", "p1", "n2"]  # one merged clock


def test_editability_rides_birth_class():
    messages = [msg("n1", "u1", "2026-08-21T10:00:00.000Z"),
                msg("p1", "c1", "2026-08-21T10:00:30.000Z", source="composer")]
    by_id = {e.node_id: e for e in build_timeline(messages, [], [])}
    assert not by_id["n1"].editable   # pulled: read-only, annotatable via AMENDS
    assert by_id["p1"].editable       # composer: journaled in-place edits


def test_rewind_fork_marks_abandoned_branch_off_path():
    # n1 -> n2 (abandoned) and n1 -> n3 -> n4 (post-rewind line, newer):
    # the tip walk keeps n1/n3/n4; n2 stays as a real, off-path event.
    messages = [
        msg("n1", "u1", "2026-08-21T10:00:00.000Z"),
        msg("n2", "a1", "2026-08-21T10:01:00.000Z", role="assistant"),
        msg("n3", "u2", "2026-08-21T10:02:00.000Z"),
        msg("n4", "a2", "2026-08-21T10:03:00.000Z", role="assistant"),
    ]
    next_pairs = [("n1", "n2"), ("n1", "n3"), ("n3", "n4")]  # two NEXT out of n1
    entries = build_timeline(messages, next_pairs, [])
    on_path = {e.node_id: e.on_active_path for e in entries}
    assert on_path == {"n1": True, "n2": False, "n3": True, "n4": True}


def test_sent_flag_from_derived_edges():
    messages = [msg("p1", "c1", "2026-08-21T10:00:00.000Z", source="composer"),
                msg("p2", "c2", "2026-08-21T10:00:10.000Z", source="composer"),
                msg("n1", "u1", "2026-08-21T10:01:00.000Z")]
    entries = build_timeline(messages, [], [("n1", "p1")])
    by_id = {e.node_id: e for e in entries}
    assert by_id["p1"].sent and not by_id["p2"].sent


def test_composer_parts_never_marked_superseded():
    # A part minted between two transcript branches must not join the
    # transcript's active-path bookkeeping.
    messages = [msg("p1", "c1", "2026-08-21T10:00:00.000Z", source="composer")]
    entries = build_timeline(messages, [], [])
    assert entries[0].on_active_path


def test_blocks_group_consecutive_superseded_runs():
    messages = [
        msg("n1", "u1", "2026-08-21T10:00:00.000Z"),
        msg("n2", "a1", "2026-08-21T10:01:00.000Z", role="assistant"),
        msg("n3", "a2", "2026-08-21T10:01:30.000Z", role="assistant"),
        msg("n4", "u2", "2026-08-21T10:02:00.000Z"),
    ]
    next_pairs = [("n1", "n2"), ("n2", "n3"), ("n1", "n4")]  # n2+n3 abandoned
    blocks = timeline_blocks(build_timeline(messages, next_pairs, []))
    kinds = [(kind, [e.node_id for e in run]) for kind, run in blocks]
    assert kinds == [("live", ["n1"]), ("superseded", ["n2", "n3"]), ("live", ["n4"])]


def test_empty_graph_is_an_empty_timeline():
    assert build_timeline([], [], []) == []
    assert timeline_blocks([]) == []
