"""Odoo-as-master-source tests (3-Jul-2026 integration).

Covers the res.partner → canonical mapping, batched fetch, source selection
(csv | odoo | auto with CSV fallback), the /master/reload endpoint, and the
importer's exact-partner-id write path. All Odoo traffic is stubbed — no
network, no real personal data.
"""
from __future__ import annotations

import base64
import importlib
from pathlib import Path

import pytest

from reconciliation.odoo_master import fetch_partners, partner_to_canonical
from reconciliation.repository import MasterRepository

FIX = Path(__file__).parent / "fixtures"
ADMIN = {"Authorization": "Basic " + base64.b64encode(b"admin@deveres.ie:Admin2026!").decode()}


def _partner(**kw) -> dict:
    base = {"id": 7, "name": "Aisling Toth", "ref": "10042", "email": "a.toth@example.ie",
            "phone": "+353 87 123 4567", "street": "4 Main Street", "street2": False,
            "city": "Greystones", "zip": "A63 XY12",
            "state_id": [101, "Wicklow (IE)"], "country_id": [103, "Ireland"],
            "is_company": False}
    base.update(kw)
    return base


class StubOdooClient:
    """Mimics pipeline.odoo_client.OdooClient._execute for search_read."""

    def __init__(self, partners: list[dict]):
        self.partners = sorted(partners, key=lambda p: p["id"])
        self.calls = []

    def _execute(self, model, method, *args, **kwargs):
        assert (model, method) == ("res.partner", "search_read")
        self.calls.append(kwargs)
        off, lim = kwargs.get("offset", 0), kwargs.get("limit", 100)
        return [dict(p) for p in self.partners[off:off + lim]]


# ── mapping ───────────────────────────────────────────────────────────────────
class TestPartnerMapping:
    def test_person_name_split_and_fields(self):
        c = partner_to_canonical(_partner())
        assert (c["first_name"], c["last_name"], c["company"]) == ("Aisling", "Toth", "")
        assert c["client_ref"] == "10042" and c["odoo_id"] == 7
        assert c["email"] == "a.toth@example.ie"
        assert c["address1"] == "4 Main Street" and c["address2"] == ""
        assert c["town"] == "Greystones" and c["postcode"] == "A63 XY12"
        assert c["county"] == "Wicklow (IE)" and c["country"] == "Ireland"

    def test_multiword_surname_stays_together(self):
        c = partner_to_canonical(_partner(name="Fintan O Byrne"))
        assert (c["first_name"], c["last_name"]) == ("Fintan", "O Byrne")

    def test_company_partner_maps_to_company_field(self):
        c = partner_to_canonical(_partner(name="Hero Gallery Ltd", is_company=True))
        assert (c["first_name"], c["last_name"]) == ("", "")
        assert c["company"] == "Hero Gallery Ltd"

    def test_missing_ref_gets_synthetic_odoo_ref(self):
        c = partner_to_canonical(_partner(ref=False, id=4242))
        assert c["client_ref"] == "ODOO-4242"

    def test_false_scalars_become_empty_strings(self):
        c = partner_to_canonical(_partner(email=False, phone=False, street=False,
                                          state_id=False, country_id=False))
        assert c["email"] == c["phone"] == c["address1"] == ""
        assert c["county"] == c["country"] == ""
        assert c["mobile"] == ""          # Odoo 19: field does not exist


# ── fetch + repository ────────────────────────────────────────────────────────
class TestFetch:
    def test_batched_fetch_gets_everything(self):
        partners = [_partner(id=i, ref=str(1000 + i)) for i in range(1, 26)]
        stub = StubOdooClient(partners)
        recs = fetch_partners(stub, batch=10)
        assert len(recs) == 25
        assert [c.get("offset", 0) for c in stub.calls] == [0, 10, 20]
        assert recs[0]["odoo_id"] == 1 and recs[-1]["odoo_id"] == 25

    def test_from_odoo_builds_matchable_index(self):
        repo = MasterRepository.from_odoo(StubOdooClient([_partner()]))
        assert repo.source == "odoo" and len(repo) == 1
        from reconciliation.engine import ReconciliationEngine
        eng = ReconciliationEngine(repo)
        res = eng.reconcile_one(0, {
            "buyer_number": "B1", "first_name": "Aisling", "last_name": "Toth",
            "email": "A.Toth@example.ie", "phone": "", "company": "",
            "address1": "4 Main St", "address2": "", "town": "Greystones",
            "county": "", "postcode": "A63XY12", "country": "", "lots": []})
        assert res.master_ref == "10042"
        assert res.classification.value in ("retain", "update")
        assert "email" in res.matched_by

    def test_swapped_name_order_still_matches(self):
        # name_key is order-independent — 'Toth Aisling' in Odoo still blocks
        repo = MasterRepository.from_odoo(StubOdooClient([_partner(name="Toth Aisling",
                                                                   email=False)]))
        eng_index = repo.index
        hits = eng_index.candidates({"first_name": "Aisling", "last_name": "Toth"})
        assert hits, "order-swapped name must still hit the blocking index"


# ── diffing vs the Odoo address shape ─────────────────────────────────────────
class TestAddressBlockEquivalence:
    """The April Odoo DB stores 'address2, address3, county' concatenated in
    street2. Values already present anywhere in the master's address block are
    formatting, not change (the 83-updates-that-were-really-0 finding, 3-Jul)."""

    def test_empty_dedicated_county_field_is_new_info_not_containment(self):
        """14-Jul 'sync perfectly': a county buried in the street2 blob is
        NOT equivalent to the state field being populated — Odoo reads the
        field. The record must classify as an update that fills state_id.
        (address1/address2 line-shuffling stays containment-equivalent.)"""
        from reconciliation.classify import classify
        from reconciliation.matching import score_pair
        mas = partner_to_canonical(_partner(
            street="18 Ard Haven", street2="Gordon avenue, Foxrock, Dublin",
            city="Bray", state_id=False))
        inc = {"first_name": "Aisling", "last_name": "Toth",
               "email": "a.toth@example.ie", "phone": "", "company": "",
               "address1": "18 Ard Haven", "address2": "Gordon avenue",
               "town": "Bray", "county": "Dublin", "postcode": "A63 XY12",
               "country": "Ireland"}
        cls, rec, conf, mb, diffs, m, why = classify(inc, score_pair(inc, mas))
        d = {x.field: x for x in diffs}
        assert cls.value == "update"
        assert d["county"].status.value == "new_info" and d["county"].significant
        # the address LINES themselves are still containment-equivalent
        assert d["address2"].status.value == "equivalent"

    def test_genuinely_new_county_still_diffs(self):
        from reconciliation.classify import diff_fields
        mas = partner_to_canonical(_partner(street2=False, state_id=False))
        d = {x.field: x for x in diff_fields(
            {"county": "Galway", "email": "a.toth@example.ie"}, mas)}
        assert d["county"].status.value == "new_info" and d["county"].significant

    def test_county_prefix_and_odoo_suffix_are_equivalent(self):
        from reconciliation.classify import diff_fields
        mas = partner_to_canonical(_partner())          # state 'Wicklow (IE)'
        d = {x.field: x for x in diff_fields({"county": "Co. Wicklow"}, mas)}
        assert d["county"].status.value == "equivalent"


# ── data-corruption guards found live on the April DB (3-Jul) ─────────────────
class TestAprilDataGuards:
    def test_scientific_notation_phone_is_unusable(self):
        from reconciliation.normalize import phone_key
        assert phone_key("3.53868E+11") == ""          # Excel float artifact
        assert phone_key("3.53868e+11") == ""
        assert phone_key("+353 87 123 4567") != ""     # real numbers unaffected

    def test_r4_strong_id_with_conflicting_name_goes_to_review(self):
        from reconciliation.classify import classify
        from reconciliation.matching import score_pair
        mas = partner_to_canonical(_partner(name="Sam Greene"))
        inc = {"first_name": "Mark", "last_name": "Sloan",
               "email": "a.toth@example.ie",            # exact email match
               "phone": "", "company": "", "address1": "4 Main Street",
               "address2": "", "town": "Greystones", "county": "",
               "postcode": "", "country": "", "email2": "",
               # a significant change rides along — that's what R4 gates
               "postcode": "D14 XY99"}
        cls, rec, conf, mb, diffs, m, why = classify(inc, score_pair(inc, mas))
        assert cls.value == "possible_duplicate"
        assert why.startswith("R4")

    def test_r4_does_not_fire_on_agreeing_names(self):
        from reconciliation.classify import classify
        from reconciliation.matching import score_pair
        mas = partner_to_canonical(_partner())          # Aisling Toth
        inc = {"first_name": "Aisling", "last_name": "Toth",
               "email": "a.toth@example.ie", "phone": "", "company": "",
               "address1": "4 Main Street", "address2": "", "town": "Greystones",
               "county": "", "postcode": "D14 XY99", "country": ""}
        cls, *_ = classify(inc, score_pair(inc, mas))
        assert cls.value == "update"                    # normal strong-ID update


# ── importer: exact partner-id write path ─────────────────────────────────────
class TestImporterPartnerId:
    def _entry(self, odoo_id=7):
        return {"session": "s", "record_index": 0, "buyer_number": "B1",
                "change_type": "update", "master_ref": "10042",
                "name": "Aisling Toth",
                "original": {"client_ref": "10042", "odoo_id": odoo_id},
                "incoming": {}, "approved": {"first_name": "Aisling",
                                             "last_name": "Toth",
                                             "email": "new@example.ie"},
                "edited_fields": [], "changed_fields": ["email"],
                "approved_by": "t", "approved_at": "now", "lots": []}

    def test_plan_carries_partner_id_from_odoo_master(self):
        from reconciliation.odoo_import import plan_from_staging
        ops = plan_from_staging([self._entry()])
        assert len(ops) == 1 and ops[0].op == "write"
        assert ops[0].partner_id == 7

    def test_resolve_prefers_verified_partner_id(self):
        from reconciliation.odoo_import import ImportOp, OdooImporter

        class C:
            def __init__(self):
                self.searches = []

            def _execute(self, model, method, *args, **kwargs):
                self.searches.append(args[0])
                if args[0] == [["id", "=", 7]]:
                    return [7]
                return []
        imp = OdooImporter(client=C())
        op = ImportOp("write", "", "10042", "A", {"email": "x@y.ie"}, partner_id=7)
        assert imp._resolve(op) == 7
        assert imp.client.searches == [[["id", "=", 7]]]   # no ref/email search needed

    def test_resolve_falls_back_when_partner_deleted(self):
        from reconciliation.odoo_import import ImportOp, OdooImporter

        class C:
            def _execute(self, model, method, *args, **kwargs):
                if args[0] == [["ref", "=", "10042"]]:
                    return [55]
                return []
        imp = OdooImporter(client=C())
        op = ImportOp("write", "", "10042", "A", {}, partner_id=999)
        assert imp._resolve(op) == 55

    def test_resolve_synthetic_odoo_ref_by_id(self):
        from reconciliation.odoo_import import ImportOp, OdooImporter

        class C:
            def _execute(self, model, method, *args, **kwargs):
                if args[0] == [["id", "=", 4242]]:
                    return [4242]
                return []
        imp = OdooImporter(client=C())
        op = ImportOp("write", "", "ODOO-4242", "A", {}, partner_id=None)
        assert imp._resolve(op) == 4242


# ── route-level source selection + /master/reload ─────────────────────────────
@pytest.fixture()
def routes(tmp_path, monkeypatch):
    monkeypatch.setenv("RECON_MASTER_CSV", str(FIX / "master_test_clients.csv"))
    monkeypatch.setenv("RECON_STAGING_DB", str(tmp_path / "staging.db"))
    monkeypatch.delenv("ODOO_URL", raising=False)
    monkeypatch.delenv("RECON_MASTER_SOURCE", raising=False)
    import reconcile_routes
    importlib.reload(reconcile_routes)
    reconcile_routes.SESSION_PATH = tmp_path / "session.json"
    reconcile_routes.SESSIONS_DIR = tmp_path / "sessions"
    reconcile_routes.AUDIT_PATH = tmp_path / "audit.log"
    return reconcile_routes


def _client(routes_mod):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(routes_mod.router)
    return TestClient(app)


class TestMasterSourceSelection:
    def test_auto_without_odoo_url_uses_csv(self, routes):
        tc = _client(routes)
        h = tc.get("/reconcile/health", headers=ADMIN).json()
        assert h["master_source"] == "csv"
        assert h["master_source_setting"] == "auto"
        assert h["master_fallback"] is None

    def test_auto_with_odoo_url_uses_odoo(self, routes, monkeypatch):
        monkeypatch.setenv("ODOO_URL", "http://stubbed")
        monkeypatch.setattr(routes.MasterRepository, "from_odoo",
                            classmethod(lambda cls, client=None: MasterRepository(
                                [partner_to_canonical(_partner())], source="odoo")))
        tc = _client(routes)
        h = tc.get("/reconcile/health", headers=ADMIN).json()
        assert h["master_source"] == "odoo"
        assert h["master_records"] == 1

    def test_auto_falls_back_to_csv_when_odoo_down(self, routes, monkeypatch):
        monkeypatch.setenv("ODOO_URL", "http://stubbed")

        def boom(cls, client=None):
            raise ConnectionError("odoo unreachable")
        monkeypatch.setattr(routes.MasterRepository, "from_odoo", classmethod(boom))
        tc = _client(routes)
        h = tc.get("/reconcile/health", headers=ADMIN).json()
        assert h["master_source"] == "csv"
        assert "odoo unreachable" in h["master_fallback"]

    def test_explicit_odoo_mode_fails_fast(self, routes, monkeypatch):
        monkeypatch.setenv("RECON_MASTER_SOURCE", "odoo")

        def boom(cls, client=None):
            raise ConnectionError("odoo unreachable")
        monkeypatch.setattr(routes.MasterRepository, "from_odoo", classmethod(boom))
        with pytest.raises(ConnectionError):
            routes._load_master()

    def test_master_reload_refetches_and_audits(self, routes, monkeypatch):
        monkeypatch.setenv("ODOO_URL", "http://stubbed")
        sizes = iter([1, 2])
        monkeypatch.setattr(routes.MasterRepository, "from_odoo",
                            classmethod(lambda cls, client=None: MasterRepository(
                                [partner_to_canonical(_partner(id=i, ref=str(i)))
                                 for i in range(1, next(sizes) + 1)], source="odoo")))
        tc = _client(routes)
        assert tc.get("/reconcile/health", headers=ADMIN).json()["master_records"] == 1
        r = tc.post("/reconcile/master/reload", headers=ADMIN)
        assert r.status_code == 200
        body = r.json()
        assert body["master_source"] == "odoo" and body["master_records"] == 2
        assert tc.get("/reconcile/health", headers=ADMIN).json()["master_records"] == 2
        audit = routes.AUDIT_PATH.read_text()
        assert "master_reload" in audit

    def test_master_reload_requires_admin(self, routes):
        tc = _client(routes)
        assert tc.post("/reconcile/master/reload").status_code == 401
