"""Unit + integration tests for the Contact Reconciliation Engine.

Run:  pytest tests/test_reconciliation.py -q
Covers normalization equivalences, matching, classification categories, the
phone-truncation and Eircode-misfiling edge cases, lots hammer=0, and an
end-to-end engine run on synthetic data. No network / no external services.
"""
from __future__ import annotations

import io
import pytest

from reconciliation import (
    Classification, MasterRepository, ReconciliationEngine, load_incoming, load_lots,
)
from reconciliation import normalize as N
from reconciliation.matching import MasterIndex, token_set_ratio


# ── Normalization ─────────────────────────────────────────────────────────────
def test_name_normalization_ignores_title_case_accents():
    assert N.normalize_name("Mrs", "Aisling ", "Tóth") == N.normalize_name("aisling", "toth")
    assert N.name_key("John", "Smith") == N.name_key("Smith", "John")

def test_email_normalization():
    assert N.normalize_email("  John.Smith@GMAIL.com ") == "john.smith@gmail.com"

@pytest.mark.parametrize("a,b", [
    ("087 2986710", "+353 87 2986710"),
    ("0872986710", "00353872986710"),
    ("+353872986710", "087-298-6710"),
])
def test_phone_equivalence(a, b):
    assert N.phone_key(a) and N.phone_key(a) == N.phone_key(b)

def test_phone_truncated_is_unusable():
    # The Blue Cubes export truncates some numbers — these must NOT match/flag.
    assert N.phone_key("35387") == ""
    assert N.phone_key("353") == ""

def test_address_abbreviation_equivalence():
    assert N.normalize_address("12 Main Street") == N.normalize_address("12 Main St.")
    assert N.normalize_address("Apartment 4, Oak Road") == N.normalize_address("Apt 4 Oak Rd")

def test_postcode_and_country_and_eircode():
    assert N.normalize_postcode("D18 XY53") == N.normalize_postcode("d18xy53") == "D18XY53"
    assert N.normalize_country("Ireland") == "IE" and N.normalize_country("UK") == "GB"
    assert N.is_eircode("D02 P283") and not N.is_eircode("Dublin 2")


# ── Matching ──────────────────────────────────────────────────────────────────
def test_token_set_ratio_order_insensitive():
    assert token_set_ratio("john smith", "smith john") == 1.0

def test_strong_email_match_scores_high():
    masters = [{"first_name": "Jane", "last_name": "Doe", "email": "jane@x.ie", "phone": "", "mobile": ""}]
    idx = MasterIndex(masters)
    c = idx.best_match({"first_name": "J", "last_name": "Doe", "email": "jane@x.ie"})
    assert c and c.score >= 0.9 and "email" in c.matched_by


# ── Classification (categories) ───────────────────────────────────────────────
def _engine(masters):
    return ReconciliationEngine(MasterRepository(masters))

def test_classify_new():
    eng = _engine([{"first_name": "Jane", "last_name": "Doe", "email": "jane@x.ie", "phone": "", "mobile": ""}])
    r = eng.reconcile_one(0, {"buyer_number": "9", "first_name": "Zoltan", "last_name": "Nemeth",
                              "email": "zoltan@new.ie", "phone": "0851112222"})
    assert r.classification == Classification.NEW

def test_classify_retain_on_cosmetic_only():
    m = [{"client_ref": "1", "first_name": "John", "last_name": "Smith", "email": "john@x.ie",
          "phone": "087 2986710", "mobile": "", "address1": "12 Main Street", "town": "Bray",
          "postcode": "A98 X1Y2", "country": "Ireland"}]
    eng = _engine(m)
    r = eng.reconcile_one(0, {"buyer_number": "1", "first_name": "JOHN", "last_name": "smith",
                              "email": "John@X.ie", "phone": "+353872986710",
                              "address1": "12 Main St.", "town": "Bray",
                              "postcode": "a98x1y2", "country": "IE"})
    assert r.classification == Classification.RETAIN and not r.changed_fields

def test_classify_update_on_new_email():
    m = [{"client_ref": "1", "first_name": "John", "last_name": "Smith", "email": "john@old.ie",
          "phone": "087 2986710", "mobile": ""}]
    eng = _engine(m)
    r = eng.reconcile_one(0, {"buyer_number": "1", "first_name": "John", "last_name": "Smith",
                              "email": "john.smith@new.ie", "phone": "087 2986710"})
    assert r.classification == Classification.UPDATE and "Email" in r.changed_fields

def test_truncated_phone_does_not_trigger_update():
    m = [{"client_ref": "1", "first_name": "Ger", "last_name": "Rabbette", "email": "g@x.ie",
          "phone": "087 2986710", "mobile": ""}]
    eng = _engine(m)
    r = eng.reconcile_one(0, {"buyer_number": "1", "first_name": "Ger", "last_name": "Rabbette",
                              "email": "g@x.ie", "phone": "35387"})
    assert r.classification == Classification.RETAIN

def test_misfiled_eircode_postcode_is_equivalent():
    # Master has the Eircode in townCity, postalCode blank; incoming has it in Postcode.
    m = [{"client_ref": "1", "first_name": "Claire", "last_name": "OMara", "email": "c@x.ie",
          "phone": "", "mobile": "", "town": "D02 P283", "postcode": ""}]
    eng = _engine(m)
    r = eng.reconcile_one(0, {"buyer_number": "1", "first_name": "Claire", "last_name": "OMara",
                              "email": "c@x.ie", "town": "Dublin 2", "postcode": "D02P283"})
    pc = next(d for d in r.diffs if d.field == "postcode")
    assert pc.status.value == "equivalent" and not pc.significant


# ── Lots import (hammer = 0) ──────────────────────────────────────────────────
def test_lots_force_hammer_zero():
    csv_text = ",,Lot Number,Seller ref,Seller Name,Title,Lot Description,Condition,Estimate From,Estimate To,Starting Bid,Reserve,Hammer,Internal Notes\n" \
               ",,1,C90,Office,Chair,desc,,€800,€1400,500,0,1500.00,note\n"
    lots = load_lots(csv_text, is_path=False)
    assert lots[0]["hammer"] == 0 and lots[0]["hammer_export"] == "1500.00"


# ── End-to-end ────────────────────────────────────────────────────────────────
def test_end_to_end_engine_summary():
    m = [{"client_ref": "1", "first_name": "John", "last_name": "Smith", "email": "john@x.ie",
          "phone": "0872986710", "mobile": ""}]
    eng = _engine(m)
    incoming_csv = ("Lot Number,Lot Title,Buyer Number,First Name,Last Name,Email,Address 1,Address 2,Town,County,Postcode,Country,Phone,Winning Bid\n"
                    "1,Chair,1,John,Smith,john@x.ie,,,,,,,+353872986710,500\n"      # retain
                    "2,Table,2,New,Person,new@y.ie,,,,,,,0851112222,300\n")          # new
    incoming = load_incoming(incoming_csv, is_path=False)
    results, summary = eng.run(incoming)
    assert summary.total == 2 and summary.new == 1 and summary.retain == 1


# ── Round 2: seller detection, decide scope, session round-trip, xlsx/pdf ────
def test_detect_and_load_seller_export():
    from reconciliation.repository import load_upload
    seller_csv = ("Seller Ref,First Name,Last Name,Company,Commission,VAT Rate,Telephone,Mobile,Email,\n"
                  "1106,James,Philips,Aline Office Furniture Limited,Default 10% +V,Margin,01-288 7796,,info@aline.ie,\n")
    kind, recs = load_upload(seller_csv)
    assert kind == "sellers" and len(recs) == 1
    assert recs[0]["company"] == "Aline Office Furniture Limited"
    buyer_csv = ("Lot Number,Lot Title,Buyer Number,First Name,Last Name,Email,Address 1,Address 2,Town,County,Postcode,Country,Phone,Winning Bid\n"
                 "1,Chair,7,A,B,a@b.ie,,,,,,,,500\n")
    kind2, recs2 = load_upload(buyer_csv)
    assert kind2 == "buyers" and len(recs2) == 1

def test_load_upload_rejects_unknown_format():
    from reconciliation.repository import load_upload
    with pytest.raises(ValueError):
        load_upload("Foo,Bar\n1,2\n")

def test_recon_result_round_trip():
    from reconciliation.models import recon_result_from_dict
    m = [{"client_ref": "1", "first_name": "John", "last_name": "Smith", "email": "john@old.ie",
          "phone": "087 2986710", "mobile": ""}]
    eng = _engine(m)
    r = eng.reconcile_one(0, {"buyer_number": "1", "first_name": "John", "last_name": "Smith",
                              "email": "john.smith@new.ie", "phone": "087 2986710"})
    r2 = recon_result_from_dict(r.to_dict(full=True))
    assert r2.classification == r.classification and r2.action == r.action
    assert len(r2.diffs) == len(r.diffs) and r2.confidence == pytest.approx(r.confidence)

def test_xlsx_and_pdf_exports():
    m = [{"client_ref": "1", "first_name": "John", "last_name": "Smith", "email": "john@x.ie",
          "phone": "0872986710", "mobile": ""}]
    eng = _engine(m)
    results, summary = eng.run([{"buyer_number": "1", "first_name": "John", "last_name": "Smith",
                                 "email": "john@x.ie", "phone": "+353872986710", "lots": []}])
    from reconciliation.export import to_xlsx, to_pdf_summary
    x = to_xlsx(results, summary); assert x[:2] == b"PK"          # zip magic
    p = to_pdf_summary(results, summary); assert p[:4] == b"%PDF"
