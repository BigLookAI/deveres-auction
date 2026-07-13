"""Final production launch hardening (13-Jul-2026 plan):

  • the deVeres production assembly ships WITHOUT sor_bidding — a completion
    push must skip the winning-bid record cleanly, not error the op;
  • lot_suffix was removed upstream (sor_events_auction 19.0.1.1.0) — the
    fetch must adapt to either schema;
  • real April-export county forms ('CO.DUBLIN', 'Dublin 8') must resolve,
    while bare 'Co…' words like Cork must never be mangled;
  • an address rewrite carries town/county/country/postcode into the same
    push so the import converges in ONE approve→push cycle.
"""
from __future__ import annotations

import pytest

from reconciliation.lots_engine import (
    reconcile_lots, plan_updates, execute_updates, bidding_installed, _lot_fields,
)
from reconciliation.odoo_import import OdooImporter, plan_from_staging
from reconciliation.validation import _county_candidates
from tests.test_lots_engine import contact, odoo_lot, StubClient


class NoBiddingClient(StubClient):
    """Odoo without sor_bidding: the module search finds nothing, and any
    sor.bid call would explode (the model does not exist there)."""

    def _execute(self, model, method, *a, **kw):
        self.calls.append((model, method, a))
        if model == "ir.module.module" and method == "search":
            return []
        if model == "sor.bid":
            raise AssertionError("sor.bid must never be touched without sor_bidding")
        if method == "read":
            return [self.read_row]
        return True


class TestNoBiddingStack:
    def _completion_ops(self):
        c = contact(odoo_id=16, conf=0.95,
                    lots=[{"lot_number": "101", "winning_bid": "450"}])
        return plan_updates(reconcile_lots([c], [odoo_lot()]))

    def test_completion_skips_winning_bid_without_sor_bidding(self, monkeypatch):
        monkeypatch.setenv("RECON_ALLOW_ODOO_WRITE", "1")
        monkeypatch.setenv("RECON_LOTS_ENABLE_BUYER", "1")
        monkeypatch.setenv("RECON_LOTS_ENABLE_SOLD", "1")
        cli = NoBiddingClient({"id": 1, "hammer_price": 450.0,
                               "buyer_id": [16, "K"], "state": "sold",
                               "auction_result": "sold"})
        out = execute_updates(self._completion_ops(), client=cli, dry_run=False)
        op = out["operations"][0]
        assert out["summary"]["error"] == 0
        assert op["result"] == "written" and op["verified"] is True
        assert op["winning_bid_skipped"] == "sor_bidding not installed"
        assert "winning_bid_created" not in op

    def test_bidding_installed_probe(self):
        assert bidding_installed(NoBiddingClient({})) is False
        assert bidding_installed(StubClient({})) is True


class SchemaClient(StubClient):
    def __init__(self, has_suffix: bool):
        super().__init__({})
        self.has_suffix = has_suffix

    def _execute(self, model, method, *a, **kw):
        self.calls.append((model, method, a))
        if method == "fields_get":
            return {"lot_suffix": {"type": "char"}} if self.has_suffix else {}
        return []


class TestLotSuffixSchemaDrift:
    def test_suffixless_schema_omits_field(self):
        assert "lot_suffix" not in _lot_fields(SchemaClient(has_suffix=False))

    def test_legacy_schema_still_requests_it(self):
        assert "lot_suffix" in _lot_fields(SchemaClient(has_suffix=True))


class TestAprilCountyForms:
    """Real values from the April Blue Cubes export (13-Jul run)."""

    def test_unspaced_co_prefix_resolves(self):
        assert "DUBLIN" in _county_candidates("CO.DUBLIN")
        assert "DUBLIN" in OdooImporter._state_name_candidates("CO.DUBLIN")

    def test_dublin_postal_districts_resolve_to_dublin(self):
        for v in ("Dublin 8", "DUBLIN 6", "Dublin 3", "Dublin 6W"):
            assert "Dublin" in _county_candidates(v), v
            assert "Dublin" in OdooImporter._state_name_candidates(v), v

    def test_bare_co_words_are_never_mangled(self):
        assert _county_candidates("Cork") == ["Cork"]
        assert OdooImporter._state_name_candidates("Cork") == ["Cork"]

    def test_genuinely_invalid_values_stay_invalid(self):
        for v in ("Wicky", "Leinster"):
            cands = {c.lower() for c in _county_candidates(v)}
            assert not cands & {"wicklow", "dublin"}


class TestAddressRewriteCarriesLocation:
    def _entry(self, changed):
        return {"change_type": "update", "master_ref": "77784",
                "name": "Emma Coonan", "changed_fields": changed,
                "edited_fields": [], "approved_by": "t", "approved_at": "t",
                "original": {"odoo_id": 90},
                "approved": {"first_name": "Emma", "last_name": "Coonan",
                             "address1": "1 New Street", "town": "Ranelagh",
                             "county": "Dublin", "country": "Ireland",
                             "postcode": "D06 XY00"}}

    def test_address_change_carries_town_county_country_postcode(self):
        ops = plan_from_staging([self._entry(["address1"])])
        v = ops[0].values
        assert v["street"] == "1 New Street"
        assert v["city"] == "Ranelagh"
        assert v["zip"] == "D06 XY00"
        assert v["__state_name"] == "Dublin"
        assert v["__country_name"] == "Ireland"

    def test_non_address_change_stays_minimal(self):
        ops = plan_from_staging([self._entry(["phone"])])
        assert "city" not in ops[0].values
        assert "__state_name" not in ops[0].values
