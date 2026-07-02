"""HTTP workflow tests: edit → approve → staging → Odoo payload → rollback,
plus RBAC, session persistence and the legacy /decide compatibility layer.

Uses the synthetic fixture master (RECON_MASTER_CSV) — no real personal data."""
from __future__ import annotations

import base64
import importlib
import json
import os
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"

ADMIN = {"Authorization": "Basic " + base64.b64encode(b"admin@deveres.ie:Admin2026!").decode()}
VIEWER = {"Authorization": "Basic " + base64.b64encode(b"viewer@deveres.ie:View2026!").decode()}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RECON_MASTER_CSV", str(FIX / "master_test_clients.csv"))
    monkeypatch.setenv("RECON_STAGING_DB", str(tmp_path / "staging.db"))
    monkeypatch.setenv("RECON_VIEWER_USER", "viewer@deveres.ie")
    monkeypatch.setenv("RECON_VIEWER_PASS", "View2026!")
    import reconcile_routes
    importlib.reload(reconcile_routes)
    reconcile_routes.SESSION_PATH = tmp_path / "session.json"
    reconcile_routes.SESSIONS_DIR = tmp_path / "sessions"
    reconcile_routes.AUDIT_PATH = tmp_path / "audit.log"
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(reconcile_routes.router)
    tc = TestClient(app)
    tc._routes = reconcile_routes
    return tc


def _upload(client):
    with open(FIX / "bluecube_test_export.csv", "rb") as f:
        r = client.post("/reconcile/upload",
                        files={"file": ("bluecube_test_export.csv", f, "text/csv")},
                        headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


def _first_index(client, state):
    rows = client.get(f"/reconcile/results?state={state}&page_size=100",
                      headers=ADMIN).json()["rows"]
    assert rows, f"no rows in state {state}"
    return rows[0]["index"]


# ── security / RBAC ───────────────────────────────────────────────────────────
class TestSecurity:
    def test_no_auth_is_401(self, client):
        assert client.get("/reconcile/results").status_code == 401

    def test_viewer_can_read_but_not_write(self, client):
        _upload(client)
        assert client.get("/reconcile/results", headers=VIEWER).status_code == 200
        assert client.get("/reconcile/progress", headers=VIEWER).status_code == 200
        idx = _first_index(client, "update_suggested")
        r = client.post(f"/reconcile/records/{idx}/approve", json={}, headers=VIEWER)
        assert r.status_code == 403
        r = client.post(f"/reconcile/records/{idx}/edit",
                        json={"fields": {"town": "X"}}, headers=VIEWER)
        assert r.status_code == 403

    def test_wrong_password_rejected(self, client):
        bad = {"Authorization": "Basic " + base64.b64encode(b"admin@deveres.ie:nope").decode()}
        assert client.get("/reconcile/results", headers=bad).status_code == 401

    def test_audit_log_written(self, client):
        _upload(client)
        idx = _first_index(client, "update_suggested")
        client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN)
        log = client._routes.AUDIT_PATH.read_text()
        events = [json.loads(l)["event"] for l in log.splitlines()]
        assert "upload" in events and "state" in events


# ── the core meeting workflow ─────────────────────────────────────────────────
class TestApprovalWorkflow:
    def test_approve_update_stages_and_updates_state(self, client):
        _upload(client)
        idx = _first_index(client, "update_suggested")
        r = client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN).json()
        assert r["state"] == "update_ready"
        stg = client.get("/reconcile/staging", headers=ADMIN).json()
        assert stg["counts"]["ready"]["update"] == 1
        assert stg["entries"][0]["change_type"] == "update"

    def test_approve_new_client_is_create(self, client):
        _upload(client)
        idx = _first_index(client, "new_record")
        r = client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN).json()
        assert r["state"] == "import_ready"
        e = client.get("/reconcile/staging", headers=ADMIN).json()["entries"][0]
        assert e["change_type"] == "create" and e["master_ref"] == ""

    def test_edit_then_approve_writes_edits_to_staging_only(self, client):
        """The Wickie→Wicklow scenario: original upload stays untouched."""
        _upload(client)
        rows = client.get("/reconcile/results?state=update_suggested&page_size=100",
                          headers=ADMIN).json()["rows"]
        target = next(r for r in rows if r["buyer_number"] == "9005")
        idx = target["index"]
        r = client.post(f"/reconcile/records/{idx}/edit",
                        json={"fields": {"county": "Wicklow"}}, headers=ADMIN).json()
        assert r["state"] == "manual_edit" and r["edits"] == {"county": "Wicklow"}
        client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN)
        e = next(x for x in client.get("/reconcile/staging", headers=ADMIN).json()["entries"]
                 if x["record_index"] == idx)
        assert e["approved"]["county"] == "Wicklow"       # edited value approved
        assert e["incoming"]["county"] == "Wickie"        # upload snapshot untouched
        assert "county" in e["edited_fields"]
        det = client.get(f"/reconcile/results/{idx}", headers=ADMIN).json()
        assert det["incoming"]["county"] == "Wickie"      # session record untouched too

    def test_edit_rejects_unknown_fields(self, client):
        _upload(client)
        idx = _first_index(client, "update_suggested")
        r = client.post(f"/reconcile/records/{idx}/edit",
                        json={"fields": {"hammer": "0"}}, headers=ADMIN)
        assert r.status_code == 400 and "not editable" in r.json()["detail"]

    def test_discard_edits_returns_to_original_state(self, client):
        _upload(client)
        idx = _first_index(client, "update_suggested")
        client.post(f"/reconcile/records/{idx}/edit",
                    json={"fields": {"town": "Elsewhere"}}, headers=ADMIN)
        r = client.delete(f"/reconcile/records/{idx}/edit", headers=ADMIN).json()
        assert r["state"] == "update_suggested"

    def test_reject_withdraws_from_staging(self, client):
        _upload(client)
        idx = _first_index(client, "update_suggested")
        client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN)
        r = client.post(f"/reconcile/records/{idx}/reject",
                        json={"reason": "not wanted"}, headers=ADMIN).json()
        assert r["state"] == "rejected"
        assert client.get("/reconcile/staging", headers=ADMIN).json()["counts"]["pending_total"] == 0

    def test_rollback_reopen_after_reject(self, client):
        _upload(client)
        idx = _first_index(client, "update_suggested")
        client.post(f"/reconcile/records/{idx}/reject", json={}, headers=ADMIN)
        r = client.post(f"/reconcile/records/{idx}/reopen", headers=ADMIN).json()
        assert r["state"] == "update_suggested"     # safe rollback, nothing lost

    def test_needs_review_resolution_both_ways(self, client):
        _upload(client)
        rows = client.get("/reconcile/results?state=needs_review&page_size=100",
                          headers=ADMIN).json()["rows"]
        assert len(rows) >= 3
        same, diff = rows[0]["index"], rows[1]["index"]
        r = client.post(f"/reconcile/records/{same}/approve", json={"as": "update"},
                        headers=ADMIN).json()
        assert r["state"] == "update_ready"
        r = client.post(f"/reconcile/records/{diff}/approve", json={"as": "new"},
                        headers=ADMIN).json()
        assert r["state"] == "import_ready"

    def test_illegal_transition_is_409_not_silent(self, client):
        _upload(client)
        idx = _first_index(client, "existing_ok")
        r = client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN)
        assert r.status_code == 409

    def test_bulk_approve_by_state(self, client):
        _upload(client)
        n_up = client.get("/reconcile/progress", headers=ADMIN).json()["by_state"]["update_suggested"]
        r = client.post("/reconcile/approve-bulk", json={"state": "update_suggested"},
                        headers=ADMIN).json()
        assert len(r["approved"]) == n_up and not r["skipped"]

    def test_history_records_every_transition(self, client):
        _upload(client)
        idx = _first_index(client, "update_suggested")
        client.post(f"/reconcile/records/{idx}/edit",
                    json={"fields": {"town": "Somewhere"}}, headers=ADMIN)
        client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN)
        h = client.get(f"/reconcile/records/{idx}/history", headers=ADMIN).json()
        states = [x["to"] for x in h["history"]]
        assert states == ["manual_edit", "update_ready"]
        assert len(h["transitions"]) == 2     # persisted in SQLite too

    def test_progress_counters_move(self, client):
        _upload(client)
        before = client.get("/reconcile/progress", headers=ADMIN).json()["by_state"]
        idx = _first_index(client, "update_suggested")
        client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN)
        after = client.get("/reconcile/progress", headers=ADMIN).json()["by_state"]
        assert after["update_suggested"] == before["update_suggested"] - 1
        assert after["update_ready"] == before["update_ready"] + 1


# ── persistence: state survives a restart ─────────────────────────────────────
class TestPersistence:
    def test_states_and_edits_survive_reload(self, client):
        _upload(client)
        idx = _first_index(client, "update_suggested")
        client.post(f"/reconcile/records/{idx}/edit",
                    json={"fields": {"county": "Wicklow"}}, headers=ADMIN)
        client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN)
        # simulate a process restart: clear in-memory state, restore from disk
        rr = client._routes
        rr._state.update(results=[], summary=None, loaded_from_disk=False)
        det = client.get(f"/reconcile/results/{idx}", headers=ADMIN).json()
        assert det["state"] == "update_ready"
        assert det["edits"] == {"county": "Wicklow"}
        assert det["history"]


# ── Odoo payload from staging ─────────────────────────────────────────────────
class TestOdooPayload:
    def test_import_refuses_empty_staging(self, client):
        _upload(client)
        r = client.post("/reconcile/odoo-import", json={}, headers=ADMIN)
        assert r.status_code == 404 and "approve" in r.json()["detail"].lower()

    def test_plan_separates_create_and_write(self, client):
        _upload(client)
        rows = client.get("/reconcile/results?page_size=100&state=all", headers=ADMIN).json()["rows"]
        helen = next(r for r in rows if r["buyer_number"] == "9010")   # mappable address move
        n = _first_index(client, "new_record")
        client.post(f"/reconcile/records/{helen['index']}/approve", json={}, headers=ADMIN)
        client.post(f"/reconcile/records/{n}/approve", json={}, headers=ADMIN)
        plan = client.post("/reconcile/odoo-import", json={"dry_run": True},
                           headers=ADMIN).json()
        s = plan["summary"]
        assert s["dry_run"] is True and s["write"] == 1 and s["create"] == 1
        ops = {o["op"]: o for o in plan["operations"]}
        assert ops["create"]["ref"].startswith("BC-")       # new → create with BC ref
        assert not ops["write"]["ref"].startswith("BC-")    # update → canonical ref

    def test_update_payload_contains_only_changed_fields(self, client):
        _upload(client)
        rows = client.get("/reconcile/results?page_size=100&state=all", headers=ADMIN).json()["rows"]
        helen = next(r for r in rows if r["buyer_number"] == "9010")
        client.post(f"/reconcile/records/{helen['index']}/approve", json={}, headers=ADMIN)
        plan = client.post("/reconcile/odoo-import", json={"dry_run": True},
                           headers=ADMIN).json()
        op = next(o for o in plan["operations"] if o["op"] == "write")
        assert "email" not in op["values"]          # unchanged fields never written
        assert op["values"].get("street") or op["values"].get("city")  # the move IS written

    def test_county_change_maps_to_state_lookup(self, client):
        """A county correction (Wickie→Wicklow) becomes a state_id lookup
        (__state_name pseudo-field) resolved at execute time — never dropped."""
        _upload(client)
        rows = client.get("/reconcile/results?state=update_suggested&page_size=100",
                          headers=ADMIN).json()["rows"]
        ciara = next(r for r in rows if r["buyer_number"] == "9005")
        client.post(f"/reconcile/records/{ciara['index']}/edit",
                    json={"fields": {"county": "Wicklow"}}, headers=ADMIN)
        client.post(f"/reconcile/records/{ciara['index']}/approve", json={}, headers=ADMIN)
        plan = client.post("/reconcile/odoo-import", json={"dry_run": True},
                           headers=ADMIN).json()
        op = next(o for o in plan["operations"] if o["op"] == "write")
        assert op["values"]["__state_name"] == "Wicklow"

    def test_lookup_resolution_on_live_execute(self, client):
        """__state_name/__country_name resolve to state_id/country_id via a
        stubbed Odoo client; unresolved names land in the comment."""
        from reconciliation.odoo_import import OdooImporter, ImportOp

        class StubClient:
            def __init__(self):
                self.calls = []
            def _execute(self, model, method, *args, **kw):
                self.calls.append((model, method, args))
                if model == "res.partner" and method == "search":
                    return [77]
                if model == "res.country":
                    return [103]                      # Ireland
                if model == "res.country.state":
                    name = args[0][0][1] if False else args[0]
                    return [55] if "Wicklow" in str(args) else []
                if method == "write":
                    return True
                return []

        import os as _os
        _os.environ["RECON_ALLOW_ODOO_WRITE"] = "1"
        try:
            imp = OdooImporter(client=StubClient())
            op = ImportOp("write", "test", "5003", "Ciara Testson",
                          {"__state_name": "Wicklow", "__country_name": "Ireland"})
            res = imp.execute([op], dry_run=False)
            values = res["operations"][0]["values"]
            assert values.get("country_id") == 103
            assert values.get("state_id") == 55
            assert "__state_name" not in values and "__country_name" not in values
            # unresolved case → comment, not silence
            op2 = ImportOp("write", "test", "5003", "X",
                           {"__state_name": "Atlantis"})
            res2 = imp.execute([op2], dry_run=False)
            assert "Atlantis" in res2["operations"][0]["values"].get("comment", "")
        finally:
            _os.environ.pop("RECON_ALLOW_ODOO_WRITE", None)

    def test_staging_purge_retention(self, client):
        """Old pushed/withdrawn rows purge; ready rows never do."""
        _upload(client)
        idx = _first_index(client, "update_suggested")
        client.post(f"/reconcile/records/{idx}/approve", json={}, headers=ADMIN)
        # ready rows survive any purge
        r = client.post("/reconcile/staging/purge", json={"retention_days": 1},
                        headers=ADMIN).json()
        assert r["purged"] == 0
        assert client.get("/reconcile/staging", headers=ADMIN).json()["counts"]["pending_total"] == 1
        # invalid retention rejected
        assert client.post("/reconcile/staging/purge", json={"retention_days": 0},
                           headers=ADMIN).status_code == 400
        # viewer can't purge
        assert client.post("/reconcile/staging/purge", json={}, headers=VIEWER).status_code == 403

    def test_master_duplicates_worksheet(self, client):
        r = client.get("/reconcile/master-quality/export", headers=ADMIN)
        assert r.status_code == 200
        header = r.text.splitlines()[0]
        assert header.startswith("matched_on,key,count")

    def test_high_value_flags_id_check(self, client):
        _upload(client)
        rows = client.get("/reconcile/results?page_size=100&state=all", headers=ADMIN).json()["rows"]
        helen = next(r for r in rows if r["buyer_number"] == "9010")    # €12,500 lot
        client.post(f"/reconcile/records/{helen['index']}/approve", json={}, headers=ADMIN)
        plan = client.post("/reconcile/odoo-import", json={"dry_run": True}, headers=ADMIN).json()
        assert plan["summary"]["id_checks_required"] == 1


# ── legacy /decide compatibility ──────────────────────────────────────────────
class TestLegacyDecide:
    def test_decide_update_now_stages(self, client):
        _upload(client)
        r = client.post("/reconcile/decide", json={"action": "UPDATE", "status": "update"},
                        headers=ADMIN).json()
        assert r["updated"] >= 1
        assert client.get("/reconcile/staging", headers=ADMIN).json()["counts"]["ready"]["update"] >= 1

    def test_decide_empty_scope_still_rejected(self, client):
        _upload(client)
        assert client.post("/reconcile/decide", json={"action": "UPDATE"},
                           headers=ADMIN).status_code == 400

    def test_results_export_csv_includes_state(self, client):
        _upload(client)
        text = client.get("/reconcile/export?fmt=csv", headers=ADMIN).text
        assert "classification" in text.splitlines()[0]
