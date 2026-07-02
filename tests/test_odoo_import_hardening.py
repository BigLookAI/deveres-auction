"""Regression tests for the 2-Jul Odoo push hardening, written against the
behaviour verified live on the restored April-test Odoo 19 instance:

  * execute_kw domain shapes (the original code over-nested domains and
    crashed on first contact with a real server — even in dry-run)
  * Odoo 19 has no res.partner.mobile → phone fallback / comment audit
  * 'Co. Wicklow' / 'N. Ireland' style county lookups
  * per-operation error isolation (one bad record never aborts the batch)
  * staging payload validation (bad rows become explicit VALIDATION skips)
  * old persisted sessions get their NEW-client diffs healed on restore
"""
from __future__ import annotations

import os

import pytest

from reconciliation.odoo_import import (
    ImportOp, OdooImporter, plan_from_staging, _apply_mobile,
)


class RecordingClient:
    """Stub OdooClient capturing every execute_kw-style call; programmable
    responses keyed by (model, method)."""

    def __init__(self, responses=None, raise_for_refs=()):
        self.calls = []
        self.responses = responses or {}
        self.raise_for_refs = set(raise_for_refs)
        self.created = []

    def _execute(self, model, method, *args, **kw):
        self.calls.append((model, method, args, kw))
        if method == "create" and args and isinstance(args[0], dict):
            if args[0].get("ref") in self.raise_for_refs:
                raise RuntimeError("boom: simulated Odoo fault")
            self.created.append(args[0])
            return 1000 + len(self.created)
        return self.responses.get((model, method), [])


def _staged_create(**over):
    entry = {
        "session": "t", "record_index": 1, "buyer_number": "9001",
        "change_type": "create", "master_ref": "", "name": "Testfirst Newclient",
        "approved": {"first_name": "Testfirst", "last_name": "Newclient",
                     "email": "t.n@example.test", "town": "Kinsale"},
        "edited_fields": [], "changed_fields": [], "lots": [],
    }
    entry.update(over)
    return entry


# ── domain shapes: the exact regression that crashed on the live server ──────
class TestDomainShapes:
    def test_resolve_searches_use_single_nested_domains(self):
        cli = RecordingClient()
        imp = OdooImporter(client=cli)
        op = ImportOp("create", "t", "BC-9001", "X",
                      {"email": "a@b.ie", "ref": "BC-9001"})
        imp._resolve(op)
        searches = [c for c in cli.calls if c[1] == "search"]
        assert searches, "resolve must search by ref/email"
        for _model, _method, args, _kw in searches:
            domain = args[0]
            for item in domain:
                # every domain item is a leaf [field, operator, value] or an
                # operator string — never another wrapped list of leaves
                assert isinstance(item, str) or (
                    len(item) == 3 and isinstance(item[0], str)), \
                    f"over-nested domain passed to execute_kw: {domain!r}"

    def test_lookup_resolution_domains_are_flat(self, monkeypatch):
        monkeypatch.setenv("RECON_ALLOW_ODOO_WRITE", "1")
        cli = RecordingClient(responses={("res.country", "search"): [101],
                                         ("res.country.state", "search"): [945]})
        imp = OdooImporter(client=cli)
        op = ImportOp("write", "t", "5003", "X",
                      {"__state_name": "Wicklow", "__country_name": "Ireland"})
        cli.responses[("res.partner", "search")] = [77]
        imp.execute([op], dry_run=False)
        for _model, _method, args, _kw in cli.calls:
            if _method != "search":
                continue
            for item in args[0]:
                assert isinstance(item, str) or len(item) == 3


# ── Odoo 19: no res.partner.mobile ────────────────────────────────────────────
class TestMobileMapping:
    def test_mobile_becomes_phone_when_phone_empty(self):
        values = {}
        _apply_mobile(values, "0871234567")
        assert values == {"phone": "0871234567"}

    def test_mobile_kept_in_comment_when_phone_set(self):
        values = {"phone": "014920000"}
        _apply_mobile(values, "0871234567")
        assert values["phone"] == "014920000"
        assert "0871234567" in values["comment"]

    def test_create_plan_never_emits_mobile_field(self):
        entry = _staged_create()
        entry["approved"]["mobile"] = "0879998877"
        ops = plan_from_staging([entry])
        assert "mobile" not in ops[0].values
        assert ops[0].values.get("phone") == "0879998877"


# ── county name candidates ────────────────────────────────────────────────────
class TestStateCandidates:
    def test_co_prefix_stripped(self):
        cands = OdooImporter._state_name_candidates("Co. Wicklow")
        assert "Wicklow" in cands and cands[0] == "Co. Wicklow"

    def test_county_prefix_stripped(self):
        assert "Dublin" in OdooImporter._state_name_candidates("County Dublin")

    def test_northern_ireland_alias(self):
        assert "Northern Ireland" in OdooImporter._state_name_candidates("N. Ireland")


# ── per-op error isolation ────────────────────────────────────────────────────
class TestErrorIsolation:
    def test_one_failed_create_does_not_abort_batch(self, monkeypatch):
        monkeypatch.setenv("RECON_ALLOW_ODOO_WRITE", "1")
        cli = RecordingClient(raise_for_refs={"BC-BAD"})
        imp = OdooImporter(client=cli)
        ops = [ImportOp("create", "t", "BC-BAD", "Bad", {"name": "Bad", "ref": "BC-BAD"}),
               ImportOp("create", "t", "BC-GOOD", "Good", {"name": "Good", "ref": "BC-GOOD"})]
        res = imp.execute(ops, dry_run=False)
        assert res["summary"]["error"] == 1
        assert res["summary"]["create"] == 1
        by_ref = {o["ref"]: o for o in res["operations"]}
        assert by_ref["BC-BAD"]["op"] == "error"
        assert "boom" in by_ref["BC-BAD"]["reason"]
        assert by_ref["BC-GOOD"]["partner_id"] == 1001

    def test_write_without_resolvable_partner_becomes_skip(self, monkeypatch):
        monkeypatch.setenv("RECON_ALLOW_ODOO_WRITE", "1")
        cli = RecordingClient()          # search always returns []
        imp = OdooImporter(client=cli)
        op = ImportOp("write", "approved update", "C-UNKNOWN", "Ghost",
                      {"city": "Naas"})
        res = imp.execute([op], dry_run=False)
        assert res["summary"]["skip"] == 1 and res["summary"]["write"] == 0
        assert "no matching partner" in res["operations"][0]["reason"]


# ── staging payload validation ────────────────────────────────────────────────
class TestPlanValidation:
    def test_nameless_row_is_validation_skip(self):
        entry = _staged_create(approved={"email": "x@y.ie"}, name="")
        ops = plan_from_staging([entry])
        assert ops[0].op == "skip" and ops[0].reason.startswith("VALIDATION")

    def test_create_without_buyer_number_is_validation_skip(self):
        entry = _staged_create(buyer_number="")
        ops = plan_from_staging([entry])
        assert ops[0].op == "skip" and "buyer number" in ops[0].reason

    def test_update_without_master_ref_is_validation_skip(self):
        entry = _staged_create(change_type="update", master_ref="")
        ops = plan_from_staging([entry])
        assert ops[0].op == "skip" and "master ref" in ops[0].reason

    def test_valid_rows_unaffected(self):
        ops = plan_from_staging([_staged_create()])
        assert ops[0].op == "create" and ops[0].ref == "BC-9001"


# ── old-session healing: NEW clients get diffs on restore ─────────────────────
class TestSessionHealing:
    def test_restored_new_record_without_diffs_gets_incoming_report(
            self, tmp_path, monkeypatch):
        import base64
        import importlib
        import json
        monkeypatch.setenv("RECON_MASTER_CSV",
                           str(os.path.join(os.path.dirname(__file__),
                                            "fixtures", "master_test_clients.csv")))
        monkeypatch.setenv("RECON_STAGING_DB", str(tmp_path / "staging.db"))
        import reconcile_routes
        importlib.reload(reconcile_routes)
        reconcile_routes.SESSION_PATH = tmp_path / "session.json"
        reconcile_routes.SESSIONS_DIR = tmp_path / "sessions"
        reconcile_routes.AUDIT_PATH = tmp_path / "audit.log"
        # a pre-fix persisted session: NEW client, empty diffs (the bug)
        session = {"filename": "old.csv", "kind": "buyers", "session_id": "old",
                   "summary": {"total": 1},
                   "results": [{
                       "index": 0, "buyer_number": "77497",
                       "incoming_name": "Fintan O Byrne",
                       "classification": "new", "recommendation": "ADD",
                       "confidence": 0.0, "matched_by": [], "master_ref": None,
                       "master_name": "", "changed_fields": [], "action": "ADD",
                       "state": "new_record", "diffs": [],
                       "incoming": {"first_name": "Fintan", "last_name": "O Byrne",
                                    "town": "Enniskerry", "county": "Co. Wicklow",
                                    "postcode": "A98 F2K7", "country": "Ireland"},
                       "master": {}, "lots": [], "edits": {},
                       "approved_values": {}, "history": [],
                       "match_evidence": {}, "review_reason": "",
                   }]}
        reconcile_routes.SESSION_PATH.write_text(json.dumps(session))
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(reconcile_routes.router)
        tc = TestClient(app)
        auth = {"Authorization": "Basic " +
                base64.b64encode(b"admin@deveres.ie:Admin2026!").decode()}
        d = tc.get("/reconcile/results/0", headers=auth).json()
        by_field = {x["field"]: x for x in d["diffs"]}
        assert by_field, "healed session must expose a field report"
        assert by_field["town"]["incoming"] == "Enniskerry"
        assert by_field["name"]["incoming"] == "Fintan O Byrne"
        assert d["changed_fields"] == []
