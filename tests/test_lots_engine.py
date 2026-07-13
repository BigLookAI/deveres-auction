"""Lot Reconciliation Engine (Phase 11+): matching by lot number only,
exception rules (missing/duplicate/conflict), idempotency, feature-flagged
buyer/sold writes, and the verified execute path."""
from __future__ import annotations

import pytest

from reconciliation.models import Classification, Recommendation, ReconResult
from reconciliation.lots_engine import (
    reconcile_lots, summarize, plan_updates, execute_updates, flags,
)


def contact(buyer="9001", name="Test Buyer", odoo_id=77, conf=0.97, lots=None):
    return ReconResult(
        index=0, buyer_number=buyer, incoming_name=name,
        classification=Classification.RETAIN,
        recommendation=Recommendation.KEEP_EXISTING, confidence=conf,
        master={"odoo_id": odoo_id} if odoo_id else {},
        lots=lots or [])


def odoo_lot(id=1, number="101", hammer=0.0, state="live", title="Lot 101"):
    return {"id": id, "lot_number": number, "hammer_price": hammer,
            "state": state, "lot_title": title, "buyer_id": False}


class TestMatching:
    def test_matches_by_lot_number_never_title(self):
        c = contact(lots=[{"lot_number": "101", "lot_title": "COMPLETELY DIFFERENT TITLE",
                           "winning_bid": "450"}])
        r = reconcile_lots([c], [odoo_lot(number="101", title="Irish Landscape")])
        assert r[0].status == "ready"
        assert r[0].odoo_lot_id == 1

    def test_missing_lot_is_exception_never_created(self):
        c = contact(lots=[{"lot_number": "999", "winning_bid": "100"}])
        r = reconcile_lots([c], [odoo_lot()])
        assert r[0].status == "missing_lot"
        assert "never" in r[0].reason.lower() or "Cannot import" in r[0].reason
        assert plan_updates(r) == []           # nothing planned for exceptions

    def test_duplicate_odoo_lots_flag_review(self):
        c = contact(lots=[{"lot_number": "105", "winning_bid": "760"}])
        r = reconcile_lots([c], [odoo_lot(id=1, number="105"),
                                 odoo_lot(id=2, number="105")])
        assert r[0].status == "duplicate_lot"
        assert r[0].candidates == [1, 2]

    def test_conflicting_bids_in_upload_flag_review(self):
        c1 = contact(buyer="9001", lots=[{"lot_number": "101", "winning_bid": "450"}])
        c2 = contact(buyer="9002", lots=[{"lot_number": "101", "winning_bid": "999"}])
        r = reconcile_lots([c1, c2], [odoo_lot(number="101")])
        assert all(x.status == "conflict" for x in r)

    def test_hammer_already_set_same_is_idempotent(self):
        c = contact(lots=[{"lot_number": "101", "winning_bid": "450"}])
        r = reconcile_lots([c], [odoo_lot(hammer=450.0)])
        assert r[0].status == "already_imported"

    def test_hammer_already_set_different_is_conflict(self):
        c = contact(lots=[{"lot_number": "101", "winning_bid": "450"}])
        r = reconcile_lots([c], [odoo_lot(hammer=300.0)])
        assert r[0].status == "conflict"
        assert "manual review" in r[0].reason.lower()

    def test_row_without_result_is_skipped(self):
        c = contact(lots=[{"lot_number": "", "winning_bid": ""}])
        r = reconcile_lots([c], [odoo_lot()])
        assert r[0].status == "no_result"

    def test_buyer_context_carried_from_contact_engine(self):
        c = contact(name="Karen Namesake", odoo_id=16, conf=0.95,
                    lots=[{"lot_number": "101", "winning_bid": "275"}])
        r = reconcile_lots([c], [odoo_lot()])
        assert r[0].buyer_name == "Karen Namesake"
        assert r[0].buyer_partner_id == 16
        assert r[0].buyer_confident is True

    def test_low_match_buyer_not_confident(self):
        c = contact(conf=0.70, lots=[{"lot_number": "101", "winning_bid": "10"}])
        r = reconcile_lots([c], [odoo_lot()])
        assert r[0].buyer_confident is False

    def test_summary_counts(self):
        c = contact(lots=[{"lot_number": "101", "winning_bid": "450"},
                          {"lot_number": "999", "winning_bid": "100"}])
        s = summarize(reconcile_lots([c], [odoo_lot()]))
        assert s["ready"] == 1 and s["missing_lot"] == 1 and s["total"] == 2


class TestPlanAndFlags:
    def _ready(self):
        c = contact(odoo_id=16, conf=0.95,
                    lots=[{"lot_number": "101", "winning_bid": "450"}])
        return reconcile_lots([c], [odoo_lot()])

    def test_default_plan_is_hammer_only(self, monkeypatch):
        monkeypatch.delenv("RECON_LOTS_ENABLE_BUYER", raising=False)
        monkeypatch.delenv("RECON_LOTS_ENABLE_SOLD", raising=False)
        ops = plan_updates(self._ready())
        assert ops[0]["values"] == {"hammer_price": 450.0}
        assert ops[0]["applied"] == ["hammer_price"]
        # buyer + sold are DESIGNED and visible in the plan as deferred
        assert any("buyer_id" in d for d in ops[0]["deferred"])
        assert any("state=sold" in d for d in ops[0]["deferred"])

    def test_flags_enable_buyer_and_sold(self, monkeypatch):
        monkeypatch.setenv("RECON_LOTS_ENABLE_BUYER", "1")
        monkeypatch.setenv("RECON_LOTS_ENABLE_SOLD", "1")
        ops = plan_updates(self._ready())
        v = ops[0]["values"]
        assert v["hammer_price"] == 450.0 and v["buyer_id"] == 16
        assert v["state"] == "sold" and v["auction_result"] == "sold"

    def test_buyer_flag_respects_confidence(self, monkeypatch):
        monkeypatch.setenv("RECON_LOTS_ENABLE_BUYER", "1")
        c = contact(odoo_id=16, conf=0.70,        # below the floor
                    lots=[{"lot_number": "101", "winning_bid": "450"}])
        ops = plan_updates(reconcile_lots([c], [odoo_lot()]))
        assert "buyer_id" not in ops[0]["values"]  # never assign uncertain buyers

    def test_estimates_and_reserve_never_written(self, monkeypatch):
        monkeypatch.setenv("RECON_LOTS_ENABLE_BUYER", "1")
        monkeypatch.setenv("RECON_LOTS_ENABLE_SOLD", "1")
        ops = plan_updates(self._ready())
        assert not {"estimate_low", "estimate_high", "reserve_price"} & set(ops[0]["values"])


class StubClient:
    def __init__(self, read_row):
        self.read_row = read_row
        self.calls = []

    def _execute(self, model, method, *a, **kw):
        self.calls.append((model, method, a))
        if method == "read":
            return [self.read_row]
        return True


class TestExecute:
    def _ops(self):
        c = contact(lots=[{"lot_number": "101", "winning_bid": "450"}])
        return plan_updates(reconcile_lots([c], [odoo_lot()]))

    def test_dry_run_never_writes(self):
        out = execute_updates(self._ops(), client=None, dry_run=True)
        assert out["summary"]["written"] == 0
        assert out["operations"][0]["result"] == "planned"

    def test_live_requires_write_gate(self, monkeypatch):
        monkeypatch.delenv("RECON_ALLOW_ODOO_WRITE", raising=False)
        with pytest.raises(PermissionError):
            execute_updates(self._ops(), client=StubClient({}), dry_run=False)

    def test_live_write_verifies_by_readback(self, monkeypatch):
        monkeypatch.setenv("RECON_ALLOW_ODOO_WRITE", "1")
        cli = StubClient({"id": 1, "hammer_price": 450.0})
        out = execute_updates(self._ops(), client=cli, dry_run=False)
        assert out["summary"]["written"] == 1
        assert out["summary"]["verified"] == 1
        assert out["operations"][0]["verified"] is True

    def test_readback_mismatch_flagged(self, monkeypatch):
        monkeypatch.setenv("RECON_ALLOW_ODOO_WRITE", "1")
        cli = StubClient({"id": 1, "hammer_price": 0.0})
        out = execute_updates(self._ops(), client=cli, dry_run=False)
        assert out["operations"][0]["verified"] is False
        assert "hammer_price" in out["operations"][0]["verify_mismatch"]


class TestSuffixAndScoping:
    def test_lot_key_forms(self):
        from reconciliation.lots_engine import lot_key
        assert lot_key("25", "A") == "25A"
        assert lot_key("25A") == "25A"
        assert lot_key("025", "a") == "25A"
        assert lot_key(" 78 ", "B") == "78B"
        assert lot_key("113") == "113"

    def test_suffix_lot_matches_combined_bluecube_form(self):
        c = contact(lots=[{"lot_number": "25A", "winning_bid": "900"}])
        lot = odoo_lot(number="25"); lot["lot_suffix"] = "A"
        r = reconcile_lots([c], [lot])
        assert r[0].status == "ready" and r[0].odoo_lot_id == 1

    def test_plain_lot_does_not_match_suffixed_sibling(self):
        c = contact(lots=[{"lot_number": "25", "winning_bid": "100"}])
        lot = odoo_lot(number="25"); lot["lot_suffix"] = "A"
        r = reconcile_lots([c], [lot])
        assert r[0].status == "missing_lot"

    def test_leading_zeros_normalised(self):
        c = contact(lots=[{"lot_number": "025", "winning_bid": "100"}])
        r = reconcile_lots([c], [odoo_lot(number="25")])
        assert r[0].status == "ready"


class TestStagedBuyerFallback:
    def test_created_contact_buyer_resolves_from_staging(self):
        c = contact(buyer="9001", name="Testfirst Newclient", odoo_id=None, conf=0.0,
                    lots=[{"lot_number": "101", "winning_bid": "450"}])
        r = reconcile_lots([c], [odoo_lot()], staged_partners={"9001": 231})
        assert r[0].buyer_partner_id == 231
        assert r[0].buyer_confident is True
        assert r[0].buyer_match == 1.0

    def test_matched_contact_ignores_staging_map(self):
        c = contact(odoo_id=16, conf=0.95,
                    lots=[{"lot_number": "101", "winning_bid": "450"}])
        r = reconcile_lots([c], [odoo_lot()], staged_partners={"9001": 999})
        assert r[0].buyer_partner_id == 16

    def test_staged_buyer_enters_plan_when_flag_on(self, monkeypatch):
        monkeypatch.setenv("RECON_LOTS_ENABLE_BUYER", "1")
        c = contact(buyer="9001", odoo_id=None, conf=0.0,
                    lots=[{"lot_number": "101", "winning_bid": "450"}])
        ops = plan_updates(reconcile_lots([c], [odoo_lot()],
                                          staged_partners={"9001": 231}))
        assert ops[0]["values"]["buyer_id"] == 231
