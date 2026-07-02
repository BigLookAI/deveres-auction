"""State-engine and staging-repository unit tests (2-Jul-2026 workflow)."""
from __future__ import annotations

import pytest

from reconciliation.staging import StagingRepository
from reconciliation.states import (
    ALLOWED_TRANSITIONS, STAGED_STATES, RecordState, TransitionError,
    initial_state, validate_transition,
)
from reconciliation.models import Classification


# ── state machine ─────────────────────────────────────────────────────────────
class TestStateMachine:
    def test_initial_states_per_classification(self):
        assert initial_state(Classification.NEW) is RecordState.NEW_RECORD
        assert initial_state(Classification.UPDATE) is RecordState.UPDATE_SUGGESTED
        assert initial_state(Classification.RETAIN) is RecordState.EXISTING_OK
        assert initial_state(Classification.POSSIBLE_DUPLICATE) is RecordState.NEEDS_REVIEW
        assert initial_state("update") is RecordState.UPDATE_SUGGESTED  # value form

    def test_happy_path_update(self):
        validate_transition(RecordState.UPDATE_SUGGESTED, RecordState.MANUAL_EDIT)
        validate_transition(RecordState.MANUAL_EDIT, RecordState.UPDATE_READY)
        validate_transition(RecordState.UPDATE_READY, RecordState.PUSHED_TO_ODOO)

    def test_happy_path_new(self):
        validate_transition(RecordState.NEW_RECORD, RecordState.IMPORT_READY)
        validate_transition(RecordState.IMPORT_READY, RecordState.PUSHED_TO_ODOO)

    def test_review_can_resolve_all_ways(self):
        for tgt in (RecordState.UPDATE_READY, RecordState.IMPORT_READY,
                    RecordState.EXISTING_OK, RecordState.REJECTED, RecordState.MANUAL_EDIT):
            validate_transition(RecordState.NEEDS_REVIEW, tgt)

    def test_pushed_is_terminal(self):
        assert ALLOWED_TRANSITIONS[RecordState.PUSHED_TO_ODOO] == set()
        with pytest.raises(TransitionError):
            validate_transition(RecordState.PUSHED_TO_ODOO, RecordState.REJECTED)

    def test_illegal_moves_raise(self):
        with pytest.raises(TransitionError):
            validate_transition(RecordState.NEW_RECORD, RecordState.UPDATE_READY)  # new can't become update
        with pytest.raises(TransitionError):
            validate_transition(RecordState.UPDATE_SUGGESTED, RecordState.PUSHED_TO_ODOO)  # must stage first
        with pytest.raises(TransitionError):
            validate_transition(RecordState.EXISTING_OK, RecordState.UPDATE_READY)  # nothing to update

    def test_self_transition_rejected(self):
        with pytest.raises(TransitionError):
            validate_transition(RecordState.REJECTED, RecordState.REJECTED)

    def test_unapprove_paths(self):
        validate_transition(RecordState.UPDATE_READY, RecordState.UPDATE_SUGGESTED)
        validate_transition(RecordState.IMPORT_READY, RecordState.NEW_RECORD)
        validate_transition(RecordState.REJECTED, RecordState.NEEDS_REVIEW)  # reopen

    def test_every_nonterminal_state_can_reach_rejected_or_pushed(self):
        for s, targets in ALLOWED_TRANSITIONS.items():
            if s in (RecordState.PUSHED_TO_ODOO, RecordState.REJECTED):
                continue
            assert targets, f"{s} is a dead end"


# ── staging repository ────────────────────────────────────────────────────────
@pytest.fixture()
def repo(tmp_path):
    return StagingRepository(tmp_path / "staging.db")


def _stage(repo, idx=1, change="update", session="s1", **kw):
    return repo.stage(
        session=session, record_index=idx, buyer_number=f"90{idx:02d}",
        change_type=change, master_ref="5001" if change == "update" else "",
        name="Aoife Samples",
        original={"town": "Howth", "county": "Dublin"},
        incoming={"town": "Howth", "county": "Wickie"},
        approved={"town": "Howth", "county": kw.get("county", "Wicklow")},
        edited_fields=kw.get("edited", ["county"]), changed_fields=["county"],
        confidence=0.97, matched_by=["email"], lots=[{"lot_number": "1", "winning_bid": "100"}],
        actor="tester@deveres.ie", note=kw.get("note", ""))


class TestStagingRepository:
    def test_stage_and_read_back(self, repo):
        _stage(repo)
        e = repo.entries("s1")[0]
        assert e["change_type"] == "update" and e["status"] == "ready"
        assert e["approved"]["county"] == "Wicklow"          # edited value
        assert e["incoming"]["county"] == "Wickie"           # original upload untouched
        assert e["original"]["county"] == "Dublin"           # master snapshot kept
        assert e["approved_by"] == "tester@deveres.ie"
        assert e["approved_at"] and e["confidence"] == 0.97
        assert e["edited_fields"] == ["county"]

    def test_upsert_no_duplicates(self, repo):
        _stage(repo); _stage(repo, county="WICKLOW RE-APPROVED")
        rows = repo.entries("s1")
        assert len(rows) == 1
        assert rows[0]["approved"]["county"] == "WICKLOW RE-APPROVED"

    def test_change_type_validated(self, repo):
        with pytest.raises(ValueError):
            _stage(repo, change="delete")

    def test_withdraw_removes_from_pending(self, repo):
        _stage(repo)
        assert repo.withdraw("s1", 1, "tester")
        assert repo.entries("s1", "ready") == []
        assert repo.entries("s1", "withdrawn")[0]["status"] == "withdrawn"
        assert not repo.withdraw("s1", 1, "tester")   # idempotent-safe: nothing ready

    def test_mark_pushed(self, repo):
        _stage(repo)
        assert repo.mark_pushed("s1", 1, odoo_partner_id=4242)
        e = repo.entries("s1", "pushed")[0]
        assert e["odoo_partner_id"] == 4242 and e["pushed_at"]

    def test_counts(self, repo):
        _stage(repo, idx=1, change="update")
        _stage(repo, idx=2, change="create")
        _stage(repo, idx=3, change="create")
        c = repo.counts("s1")
        assert c["ready"] == {"update": 1, "create": 2} and c["pending_total"] == 3

    def test_sessions_isolated(self, repo):
        _stage(repo, session="s1"); _stage(repo, session="s2")
        assert len(repo.entries("s1")) == 1 and len(repo.entries("s2")) == 1

    def test_csv_export_unambiguous_change_type(self, repo):
        _stage(repo, idx=1, change="update")
        _stage(repo, idx=2, change="create")
        csv_text = repo.export_csv("s1")
        assert "UPDATE" in csv_text and "CREATE" in csv_text
        header = csv_text.splitlines()[0]
        assert header.startswith("change_type,") and "approved_by" in header

    def test_json_export(self, repo):
        import json
        _stage(repo)
        d = json.loads(repo.export_json("s1"))
        assert d["counts"]["pending_total"] == 1 and d["entries"][0]["name"] == "Aoife Samples"

    def test_transition_log_history(self, repo):
        repo.log_transition("s1", 1, "update_suggested", "manual_edit", "tester", "edited county")
        repo.log_transition("s1", 1, "manual_edit", "update_ready", "tester", "approved")
        h = repo.history("s1", 1)
        assert [x["to_state"] for x in h] == ["manual_edit", "update_ready"]
        assert h[0]["actor"] == "tester"
