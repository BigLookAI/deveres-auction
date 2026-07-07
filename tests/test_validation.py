"""Phase 4 P2/P3: metadata-aware validation — the Wiki/Wicklow meeting case.

An incoming dropdown value that is not a valid Odoo selection must
  1. classify the record into Manual Review with a plain-English reason,
  2. refuse approval (409, with nearest-match suggestions),
  3. refuse an edit that introduces another invalid value (400),
  4. accept a corrected value and flow normally afterwards,
  5. be refused by the importer even if a legacy staged row carries one.
No silent failures anywhere.
"""
from __future__ import annotations

import base64
import importlib
from pathlib import Path

import pytest

from reconciliation.odoo_fields import static_schema, OdooFieldSchema
from reconciliation.validation import (
    validate_incoming, blocking_issues, unresolved_blocking, issues_from_dicts,
)

FIX = Path(__file__).parent / "fixtures"
ADMIN = {"Authorization": "Basic " + base64.b64encode(b"admin@deveres.ie:Admin2026!").decode()}


# ── unit: the validator itself ────────────────────────────────────────────────
class TestValidator:
    def setup_method(self):
        self.schema = static_schema([])

    def test_invalid_county_is_blocking_with_suggestion(self):
        issues = validate_incoming({"county": "Wickie"}, self.schema)
        bad = blocking_issues(issues)
        assert len(bad) == 1
        assert bad[0].field == "county" and bad[0].kind == "invalid_selection"
        assert "Wicklow" in bad[0].suggestions
        assert "Wickie" in bad[0].message

    def test_valid_county_forms_pass(self):
        for v in ("Wicklow", "wicklow", "Co. Wicklow", "County Wicklow",
                  "Waterford", "Cork."):
            assert not validate_incoming({"county": v}, self.schema), v

    def test_meeting_value_wiki_flags(self):
        bad = blocking_issues(validate_incoming({"county": "Wiki"}, self.schema))
        assert bad and "Wicklow" in bad[0].suggestions

    def test_invalid_country_flags(self):
        bad = blocking_issues(validate_incoming({"country": "Irlandia"}, self.schema))
        assert bad and bad[0].field == "country"
        assert "Ireland" in bad[0].suggestions

    def test_suspect_email_and_phone_warn_but_never_block(self):
        issues = validate_incoming({"email": "not-an-email", "phone": "35387"},
                                   self.schema)
        assert {i.kind for i in issues} == {"suspect_email", "unusable_phone"}
        assert not blocking_issues(issues)

    def test_edit_resolves_blocking_issue(self):
        issues = issues_from_dicts(
            [i.to_dict() for i in validate_incoming({"county": "Wickie"}, self.schema)])
        assert unresolved_blocking(issues, {}, self.schema)
        assert not unresolved_blocking(issues, {"county": "Wicklow"}, self.schema)
        assert not unresolved_blocking(issues, {"county": ""}, self.schema)  # cleared
        assert unresolved_blocking(issues, {"county": "Wikiland"}, self.schema)

    def test_field_types_come_from_metadata(self):
        assert self.schema.field_type("county") == "many2one"
        assert self.schema.field_type("email") == "char"
        assert self.schema.field_meta("county")["relation"] == "res.country.state"


# ── API: the full workflow around an invalid dropdown value ──────────────────
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RECON_MASTER_CSV", str(FIX / "master_test_clients.csv"))
    monkeypatch.setenv("RECON_STAGING_DB", str(tmp_path / "staging.db"))
    monkeypatch.delenv("ODOO_URL", raising=False)
    monkeypatch.delenv("RECON_MASTER_SOURCE", raising=False)
    from reconciliation import odoo_fields
    odoo_fields.invalidate_cache()          # schema cache must not leak between tests
    import reconcile_routes
    importlib.reload(reconcile_routes)
    reconcile_routes.SESSION_PATH = tmp_path / "session.json"
    reconcile_routes.SESSIONS_DIR = tmp_path / "sessions"
    reconcile_routes.AUDIT_PATH = tmp_path / "audit.log"
    reconcile_routes.SYNC_PATH = tmp_path / "sync.json"
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(reconcile_routes.router)
    return TestClient(app)


def _upload(client):
    with open(FIX / "bluecube_test_export.csv", "rb") as f:
        r = client.post("/reconcile/upload",
                        files={"file": ("bluecube_test_export.csv", f, "text/csv")},
                        headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


def _ciara(client):
    rows = client.get("/reconcile/results?state=all&page_size=100",
                      headers=ADMIN).json()["rows"]
    return next(r for r in rows if r["buyer_number"] == "9005")


class TestInvalidDropdownWorkflow:
    def test_invalid_county_forces_manual_review(self, client):
        _upload(client)
        c = _ciara(client)
        assert c["state"] == "needs_review"
        assert c["invalid"] is True
        det = client.get(f"/reconcile/results/{c['index']}", headers=ADMIN).json()
        assert "R5 INVALID_SELECTION" in det["review_reason"]
        assert det["validation_issues"][0]["suggestions"][0] == "Wicklow"

    def test_approve_without_correction_is_409_with_suggestion(self, client):
        _upload(client)
        c = _ciara(client)
        r = client.post(f"/reconcile/records/{c['index']}/approve",
                        json={"as": "update"}, headers=ADMIN)
        assert r.status_code == 409
        assert "Wicklow" in r.json()["detail"]

    def test_edit_to_another_invalid_value_is_400(self, client):
        _upload(client)
        c = _ciara(client)
        r = client.post(f"/reconcile/records/{c['index']}/edit",
                        json={"fields": {"county": "Wikiland"}}, headers=ADMIN)
        assert r.status_code == 400
        assert "not in the Odoo selection list" in r.json()["detail"]

    def test_corrected_value_flows_to_staging_and_plan(self, client):
        _upload(client)
        c = _ciara(client)
        assert client.post(f"/reconcile/records/{c['index']}/edit",
                           json={"fields": {"county": "Wicklow"}},
                           headers=ADMIN).status_code == 200
        r = client.post(f"/reconcile/records/{c['index']}/approve",
                        json={}, headers=ADMIN)
        assert r.status_code == 200 and r.json()["state"] == "update_ready"
        plan = client.post("/reconcile/odoo-import", json={"dry_run": True},
                           headers=ADMIN).json()
        op = next(o for o in plan["operations"] if o["ref"] == "5003")
        assert op["op"] == "write"
        assert op["values"]["__state_name"] == "Wicklow"

    def test_legacy_staged_invalid_value_is_refused_by_planner(self, client):
        """Belt & braces: a staged row carrying an invalid county (e.g. staged
        before this validation existed) becomes an explicit VALIDATION skip."""
        from reconciliation.odoo_import import plan_from_staging
        schema = static_schema([])
        entry = {"session": "t", "record_index": 1, "buyer_number": "9005",
                 "change_type": "update", "master_ref": "5003",
                 "name": "Ciara Testson",
                 "approved": {"first_name": "Ciara", "last_name": "Testson",
                              "county": "Wickie"},
                 "edited_fields": [], "changed_fields": ["county"], "lots": []}
        ops = plan_from_staging([entry], schema=schema)
        assert ops[0].op == "skip"
        assert "invalid County" in ops[0].reason
        assert "Wicklow" in ops[0].reason

    def test_metadata_endpoint(self, client):
        _upload(client)
        m = client.get("/reconcile/odoo-metadata", headers=ADMIN).json()
        assert m["source"] == "static"          # hermetic env — no Odoo
        assert m["fields"]["state_id"]["type"] == "many2one"
        assert m["counties"] >= 26

    def test_activity_endpoint_lists_audit_events(self, client):
        _upload(client)
        c = _ciara(client)
        client.post(f"/reconcile/records/{c['index']}/edit",
                    json={"fields": {"county": "Wicklow"}}, headers=ADMIN)
        ev = client.get("/reconcile/activity?session_only=false",
                        headers=ADMIN).json()["events"]
        kinds = {e["event"] for e in ev}
        assert "upload" in kinds and ("edit" in kinds or "state" in kinds)
