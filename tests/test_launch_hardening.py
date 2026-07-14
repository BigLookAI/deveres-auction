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


class TestFullAddressBlockWrite:
    """14-Jul (Eileen Costelloe #81012): only postcode+country were NEW_INFO,
    so the push landed just zip+country — leaving city/state empty and the
    'Dublin 6W NP48' blob inside street2. ANY address-family change now
    writes the whole approved block, so Odoo matches the Final Approved
    column field-for-field in one pass."""

    def _entry(self, changed):
        return {"change_type": "update", "master_ref": "81012",
                "name": "Eileen Costelloe", "changed_fields": changed,
                "edited_fields": [], "approved_by": "t", "approved_at": "t",
                "original": {"odoo_id": 13599},
                "approved": {"first_name": "Eileen", "last_name": "Costelloe",
                             "address1": "32 cypress Park",
                             "address2": "Templeogue", "town": "Dublin",
                             "county": "Dublin", "postcode": "d6w np48",
                             "country": "Ireland"}}

    def test_postcode_only_change_writes_whole_block(self):
        ops = plan_from_staging([self._entry(["postcode", "country"])])
        v = ops[0].values
        assert v["zip"] == "d6w np48"
        assert v["street"] == "32 cypress Park"
        assert v["street2"] == "Templeogue"        # blob normalised away
        assert v["city"] == "Dublin"
        assert v["__state_name"] == "Dublin"
        assert v["__country_name"] == "Ireland"

    def test_town_only_change_also_writes_whole_block(self):
        v = plan_from_staging([self._entry(["town"])])[0].values
        assert v["city"] == "Dublin" and v["street2"] == "Templeogue"

    def test_non_address_change_untouched(self):
        entry = self._entry(["phone"])
        entry["approved"]["phone"] = "851404274"
        v = plan_from_staging([entry])[0].values
        assert "city" not in v and "street" not in v


class TestConvergenceTails:
    """The two 14-Jul non-converging tails from the live April run."""

    def test_dublin_postal_district_county_is_equivalent(self):
        from reconciliation import normalize as N
        assert N.county_key("Dublin 4") == N.county_key("Dublin")
        assert N.county_key("DUBLIN 6W") == N.county_key("Dublin (IE)")
        assert N.county_key("Co.Dublin") == N.county_key("Dublin")
        assert N.county_key("Cork") != N.county_key("Dublin")  # no mangling

    def test_unresolved_county_marker_converges(self):
        from reconciliation.classify import diff_fields
        from reconciliation.odoo_master import partner_to_canonical
        mas = partner_to_canonical({
            "id": 9, "name": "Paula Britton", "ref": "79383",
            "email": "p@example.test", "phone": "", "is_company": False,
            "street": "5 Main St", "street2": False, "city": "Enniskillen",
            "zip": "BT74", "state_id": False, "country_id": [101, "Ireland"],
            "comment": "<p>Unresolved location values (set manually): "
                       "county/state=Co. Fermanagh</p>"})
        d = {x.field: x for x in diff_fields(
            {"county": "Co. Fermanagh", "town": "Enniskillen",
             "email": "p@example.test"}, mas)}
        assert d["county"].status.value == "equivalent"
        # a DIFFERENT county than the noted one still surfaces
        d2 = {x.field: x for x in diff_fields(
            {"county": "Tyrone", "email": "p@example.test"}, mas)}
        assert d2["county"].status.value == "new_info"


class TestRedundantStreet2Clearing:
    """14-Jul (Fionnuala Dooley #79198): Final Approved showed Address 2
    empty, but Odoo kept the 'Greystones, Wicklow' blob — its content now
    lives in City/State. A fully-redundant street2 is flagged and cleared;
    a street2 holding unique information is never touched."""

    INC = {"first_name": "Fionnuala", "last_name": "Dooley",
           "email": "fd59@example.test", "phone": "0879198258",
           "address1": "13 La Touche Close", "address2": "",
           "town": "Greystones", "county": "Wicklow",
           "postcode": "A63 DC64", "country": "Ireland"}

    def _mas(self, street2):
        from reconciliation.odoo_master import partner_to_canonical
        return partner_to_canonical({
            "id": 7, "name": "Fionnuala Dooley", "ref": "79198",
            "email": "fd59@example.test", "phone": "0879198258",
            "is_company": False, "street": "13 La Touche Close",
            "street2": street2, "city": "Greystones",
            "state_id": [111, "Wicklow (IE)"], "zip": "A63 DC64",
            "country_id": [101, "Ireland"], "comment": False})

    def test_redundant_blob_is_flagged_for_clearing(self):
        from reconciliation.classify import diff_fields
        d = {x.field: x for x in diff_fields(self.INC, self._mas("Greystones, Wicklow"))}
        assert d["address2"].status.value == "changed" and d["address2"].significant

    def test_unique_street2_is_never_overwritten(self):
        from reconciliation.classify import diff_fields
        d = {x.field: x for x in diff_fields(self.INC, self._mas("Apartment 4B"))}
        assert d["address2"].status.value == "missing"

    def test_plan_clears_redundant_street2(self):
        entry = {"change_type": "update", "master_ref": "79198",
                 "name": "Fionnuala Dooley", "changed_fields": ["address2"],
                 "edited_fields": [], "approved_by": "t", "approved_at": "t",
                 "original": {"odoo_id": 7, "address2": "Greystones, Wicklow"},
                 "approved": dict(self.INC)}
        v = plan_from_staging([entry])[0].values
        assert v["street2"] is False               # explicit clear
        assert v["city"] == "Greystones"

    def test_plan_keeps_unique_street2(self):
        entry = {"change_type": "update", "master_ref": "79198",
                 "name": "Fionnuala Dooley", "changed_fields": ["town"],
                 "edited_fields": [], "approved_by": "t", "approved_at": "t",
                 "original": {"odoo_id": 7, "address2": "Apartment 4B"},
                 "approved": dict(self.INC)}
        v = plan_from_staging([entry])[0].values
        assert "street2" not in v


class TestExplicitEditToEmpty:
    """14-Jul (Eileen #81012, operator test): Address 2 EDITED to empty must
    clear street2 in Odoo — Final Approved is the contract; the
    never-write-empty guard only protects against accidental source blanks."""

    def _entry(self):
        return {"change_type": "update", "master_ref": "81012",
                "name": "Eileen Costelloe",
                "changed_fields": ["town", "county", "postcode", "country"],
                "edited_fields": ["address2", "town"],
                "approved_by": "t", "approved_at": "t",
                "original": {"odoo_id": 13599,
                             "address2": "Templeogue, Dublin 6W NP48"},
                "approved": {"first_name": "Eileen", "last_name": "Costelloe",
                             "address1": "32 cypress Park", "address2": "",
                             "town": "Templeogue", "county": "Dublin",
                             "postcode": "d6w np48", "country": "Ireland"}}

    def test_edited_empty_address2_clears_street2(self):
        v = plan_from_staging([self._entry()])[0].values
        assert v["street2"] is False
        assert v["city"] == "Templeogue"
        assert v["__state_name"] == "Dublin"

    def test_edited_empty_county_clears_state(self):
        e = self._entry()
        e["edited_fields"] = ["county"]
        e["approved"]["county"] = ""
        e["approved"]["address2"] = "Templeogue"
        v = plan_from_staging([e])[0].values
        assert v["state_id"] is False and "__state_name" not in v
