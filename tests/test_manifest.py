"""Pending-send manifests: compose, persist, reconcile-by-exact-match."""

from cjm_session_scratchpad_qt.manifest import (
    PendingSend, compose_text, load_pending, manifest_path, reconcile, save_pending)


def test_compose_joins_parts_as_paragraphs():
    assert compose_text(["one\n", " two", "three"]) == "one\n\ntwo\n\nthree"


def test_roundtrip_persists_atomically(tmp_path):
    path = manifest_path(tmp_path, "2026-08-21_11-26-36")
    pending = [PendingSend(part_uuids=["c1", "c2"], text="one\n\ntwo")]
    save_pending(path, pending)
    loaded = load_pending(path)
    assert [p.part_uuids for p in loaded] == [["c1", "c2"]]
    assert loaded[0].text == "one\n\ntwo"


def test_missing_or_corrupt_sidecar_is_empty(tmp_path):
    assert load_pending(tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_pending(bad) == []


def test_reconcile_exact_match_yields_derivation():
    pending = [PendingSend(part_uuids=["c1", "c2"], text="one\n\ntwo")]
    pulled = [{"source_uuid": "u7", "text": "one\n\ntwo\n"}]  # trailing ws tolerated
    derivations, remaining = reconcile(pending, pulled)
    assert derivations == [("u7", ["c1", "c2"])]
    assert remaining == []


def test_reconcile_near_match_stays_pending():
    # Anything less than exact is the HITL lane's business, never an auto-mint.
    pending = [PendingSend(part_uuids=["c1"], text="one two three")]
    pulled = [{"source_uuid": "u7", "text": "one two three four"}]
    derivations, remaining = reconcile(pending, pulled)
    assert derivations == []
    assert [p.part_uuids for p in remaining] == [["c1"]]


def test_reconcile_claims_each_message_once():
    # Two identical manifests cannot both bind the same transcript message.
    pending = [PendingSend(part_uuids=["c1"], text="same"),
               PendingSend(part_uuids=["c2"], text="same")]
    pulled = [{"source_uuid": "u1", "text": "same"}]
    derivations, remaining = reconcile(pending, pulled)
    assert derivations == [("u1", ["c1"])]
    assert [p.part_uuids for p in remaining] == [["c2"]]
