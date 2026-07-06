"""The public works hub (/hub) and its wiring (6-Jul-2026)."""
from fastapi.testclient import TestClient

import recon_app


def test_hub_is_public_and_lists_all_works():
    tc = TestClient(recon_app.app)
    r = tc.get("/hub")                      # no auth required by design
    assert r.status_code == 200
    body = r.text
    for needle in ("Contact Reconciliation", "Bidder Evaluation", "Odoo Integration",
                   "/reconcile", "/bidder", "synthetic"):
        assert needle in body, f"hub page missing: {needle}"


def test_old_overview_redirects_to_hub():
    tc = TestClient(recon_app.app)
    r = tc.get("/overview", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/hub"


def test_landing_links_to_hub():
    tc = TestClient(recon_app.app)
    assert "/hub" in tc.get("/").text
