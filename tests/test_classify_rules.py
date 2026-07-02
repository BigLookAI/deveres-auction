"""Classifier rules (incl. the three manual-review rules), match evidence, and
full-dataset pathway coverage with the synthetic Blue Cubes fixture."""
from __future__ import annotations

from pathlib import Path

import pytest

from reconciliation.classify import classify, MATCH_THRESHOLD, REVIEW_FLOOR
from reconciliation.engine import ReconciliationEngine
from reconciliation.matching import MasterIndex
from reconciliation.models import Classification
from reconciliation.repository import MasterRepository, load_incoming
from reconciliation.states import RecordState

FIX = Path(__file__).parent / "fixtures"


def _mk_master(**kw):
    base = {"client_ref": "5000", "first_name": "", "last_name": "", "company": "",
            "email": "", "phone": "", "mobile": "", "address1": "", "address2": "",
            "address3": "", "town": "", "county": "", "country": "", "postcode": ""}
    base.update(kw)
    return base


def _mk_inc(**kw):
    base = {"buyer_number": "9999", "first_name": "", "last_name": "", "company": "",
            "email": "", "phone": "", "address1": "", "address2": "", "town": "",
            "county": "", "country": "", "postcode": "", "lots": []}
    base.update(kw)
    return base


def _classify(inc, masters):
    cand = MasterIndex(masters).best_match(inc)
    return classify(inc, cand)


# ── the three documented manual-review rules ──────────────────────────────────
class TestManualReviewRules:
    def test_r1_uncertain_score_band(self):
        """Same name, very different address, no country on either side →
        weighted score lands in [0.55, 0.72) with no strong identifier → R1."""
        mas = _mk_master(first_name="John", last_name="Commonname",
                         address1="71 Patrick Street", town="Kilkenny", county="Kilkenny",
                         postcode="R95TE12")
        inc = _mk_inc(first_name="John", last_name="Commonname",
                      address1="3 River Walk", town="Cork", county="Cork")
        cls, rec, conf, mb, diffs, m, reason = _classify(inc, [mas])
        assert cls is Classification.POSSIBLE_DUPLICATE
        assert reason.startswith("R1"), reason
        assert REVIEW_FLOOR <= conf < MATCH_THRESHOLD

    def test_r2_conflict_without_strong_id(self):
        """Same name AND agreeing country push the score over 0.72, but the
        address CONFLICTS and there is no email/phone — could be a namesake → R2."""
        mas = _mk_master(first_name="Liam", last_name="Conflicted",
                         address1="15 Elm Terrace", town="Dundalk", county="Louth",
                         country="Ireland", postcode="A91TE14")
        inc = _mk_inc(first_name="Liam", last_name="Conflicted",
                      address1="40 Oak Avenue", town="Waterford", county="Waterford",
                      country="Ireland", postcode="X91TE14")
        cls, rec, conf, mb, diffs, m, reason = _classify(inc, [mas])
        assert cls is Classification.POSSIBLE_DUPLICATE
        assert reason.startswith("R2"), reason

    def test_r3_name_only_additions(self):
        """Master row holds only a name; incoming wants to attach an address to
        that namesake → R3 (human confirms it's the same person)."""
        mas = _mk_master(first_name="Karen", last_name="Namesake")
        inc = _mk_inc(first_name="Karen", last_name="Namesake",
                      address1="55 Hillside Grove", town="Limerick", county="Limerick",
                      postcode="V94TE13")
        cls, rec, conf, mb, diffs, m, reason = _classify(inc, [mas])
        assert cls is Classification.POSSIBLE_DUPLICATE
        assert reason.startswith("R3"), reason

    def test_strong_id_bypasses_all_review_rules(self):
        """An exact email match is decisive even with a conflicting address."""
        mas = _mk_master(first_name="Helen", last_name="Addressmove",
                         email="helen.addressmove@example.test",
                         address1="2 Old Town Square", town="Oranmore", county="Galway")
        inc = _mk_inc(first_name="Helen", last_name="Addressmove",
                      email="helen.addressmove@example.test",
                      address1="88 Ocean Drive", town="Salthill", county="Galway")
        cls, rec, conf, mb, diffs, m, reason = _classify(inc, [mas])
        assert cls is Classification.UPDATE and reason == ""
        assert conf >= 0.90        # strong-ID floor

    def test_namesake_no_longer_becomes_update(self):
        """Regression: pre-2-Jul the John Murphy Galway/Dublin case classified
        as UPDATE (score 0.73) and would have overwritten a different person."""
        mas = _mk_master(first_name="John", last_name="Murphy",
                         address1="117 Rathgar Avenue", town="Dublin", county="Dublin",
                         country="Ireland", postcode="D06XY45")
        inc = _mk_inc(first_name="John", last_name="Murphy",
                      address1="4 Sea Road", town="Galway", county="Galway",
                      country="Ireland")
        cls, *_rest, reason = _classify(inc, [mas])
        assert cls is Classification.POSSIBLE_DUPLICATE


# ── company rename + evidence ────────────────────────────────────────────────
class TestEvidenceAndCompany:
    def test_company_rename_is_significant_update(self):
        mas = _mk_master(first_name="Ian", last_name="Companychange",
                         email="ian.companychange@example.test", company="Old Ventures Ltd")
        inc = _mk_inc(first_name="Ian", last_name="Companychange",
                      email="ian.companychange@example.test", company="New Horizons Ltd")
        cls, rec, conf, mb, diffs, m, reason = _classify(inc, [mas])
        assert cls is Classification.UPDATE
        assert any(d.field == "company" and d.significant for d in diffs)

    def test_match_evidence_breakdown(self):
        masters = [_mk_master(first_name="Aoife", last_name="Samples",
                              email="aoife.samples@example.test", mobile="+353860000002",
                              address1="8 Harbour View", town="Howth", postcode="D13TE02")]
        engine = ReconciliationEngine(MasterRepository(masters))
        inc = _mk_inc(first_name="Aoife", last_name="Samples",
                      email="aoife.samples@example.test", phone="+353 86 000 0002",
                      address1="8 Harbour View", town="Howth", postcode="D13 TE02")
        r = engine.reconcile_one(0, inc)
        ev = r.match_evidence
        assert ev["fields"]["email"]["exact"] is True
        assert ev["fields"]["phone"]["exact"] is True
        assert 0 < ev["fields"]["name"]["similarity"] <= 1
        assert abs(sum(f["contribution"] for f in ev["fields"].values())
                   - ev["weighted_score"]) < 1e-6
        assert ev["final_confidence"] == r.confidence

    def test_new_record_has_empty_evidence(self):
        engine = ReconciliationEngine(MasterRepository([_mk_master(first_name="Zz", last_name="Qq")]))
        r = engine.reconcile_one(0, _mk_inc(first_name="Testfirst", last_name="Newclient",
                                            email="x@example.test"))
        assert r.classification is Classification.NEW and r.match_evidence == {}
        assert r.state is RecordState.NEW_RECORD

    def test_new_record_diffs_populate_incoming_column(self):
        """A NEW client must carry a full field report (incoming vs empty
        master) so the review drawer shows what will be created — regression
        test for the blank Incoming column (2-Jul)."""
        engine = ReconciliationEngine(MasterRepository([_mk_master(first_name="Zz", last_name="Qq")]))
        r = engine.reconcile_one(0, _mk_inc(
            first_name="Fintan", last_name="O Byrne", email="fintan@example.test",
            phone="0871234567", address1="1 Test Road", town="Dublin",
            county="Dublin", postcode="D01 X2Y3", country="Ireland"))
        assert r.classification is Classification.NEW
        by_field = {d.field: d for d in r.diffs}
        for f in ("name", "email", "phone", "address1", "town", "county",
                  "postcode", "country"):
            assert f in by_field, f"NEW client diff report missing '{f}'"
            assert by_field[f].incoming, f"'{f}' incoming value must be populated"
            assert not by_field[f].current, f"'{f}' has no master value"
        # but nothing "changes" in the master — there is no master record
        assert r.changed_fields == []
        assert r.master == {} and r.master_ref is None


# ── full fixture dataset: every pathway ───────────────────────────────────────
@pytest.fixture(scope="module")
def fixture_results():
    master = MasterRepository.from_csv(FIX / "master_test_clients.csv")
    incoming = load_incoming(str(FIX / "bluecube_test_export.csv"))
    results, summary = ReconciliationEngine(master).run(incoming)
    return {r.buyer_number: r for r in results}, summary


class TestFixtureDataset:
    def test_every_pathway_is_present(self, fixture_results):
        _, s = fixture_results
        assert s.new >= 1 and s.retain >= 1 and s.update >= 1 and s.manual_review >= 3

    def test_completely_new_client(self, fixture_results):
        rs, _ = fixture_results
        assert rs["9001"].classification is Classification.NEW
        assert rs["9001"].state is RecordState.NEW_RECORD

    def test_duplicate_email_and_phone_both_match_same_master(self, fixture_results):
        rs, _ = fixture_results
        assert rs["9002"].master_ref == "5001" and rs["9003"].master_ref == "5001"
        for b in ("9002", "9003"):
            assert "email" in rs[b].matched_by and rs[b].confidence >= 0.90

    def test_surname_typo_still_matches_via_email(self, fixture_results):
        rs, _ = fixture_results   # O Testor vs O'Tester
        assert rs["9004"].master_ref == "5002"
        assert rs["9004"].classification in (Classification.RETAIN, Classification.UPDATE)

    def test_county_typo_wickie_flagged_for_update(self, fixture_results):
        rs, _ = fixture_results   # phone matches; county Wickie vs Wicklow
        r = rs["9005"]
        assert "phone" in r.matched_by
        assert r.classification is Classification.UPDATE
        assert any(d.field == "county" for d in r.diffs if d.significant is False or True)

    def test_missing_postcode_never_erases_master(self, fixture_results):
        rs, _ = fixture_results
        r = rs["9006"]
        pc = next(d for d in r.diffs if d.field == "postcode")
        assert pc.status.value == "missing" and not pc.significant

    def test_missing_email_and_country_phone_format_equivalent(self, fixture_results):
        rs, _ = fixture_results
        r = rs["9007"]            # 090 000007 vs +35390000007
        assert r.classification is Classification.RETAIN
        assert "phone" in r.matched_by

    def test_caps_spacing_dialcode_are_formatting_only(self, fixture_results):
        rs, _ = fixture_results
        r = rs["9008"]            # CAPS email, 00353 phone, double spaces
        assert r.classification is Classification.RETAIN
        assert not r.changed_fields

    def test_address_abbreviation_rd_equals_road(self, fixture_results):
        rs, _ = fixture_results
        assert rs["9009"].classification is Classification.RETAIN

    def test_genuine_address_move_is_update_with_id_check_value(self, fixture_results):
        rs, _ = fixture_results
        r = rs["9010"]
        assert r.classification is Classification.UPDATE
        assert any(d.field in ("address1", "town") and d.significant for d in r.diffs)
        assert sum(float(l["winning_bid"]) for l in r.lots) > 10_000

    def test_manual_review_examples_r1_r2_r3(self, fixture_results):
        rs, _ = fixture_results
        assert rs["9012"].review_reason.startswith("R1")
        assert rs["9014"].review_reason.startswith("R2")
        assert rs["9013"].review_reason.startswith("R3")
        for b in ("9012", "9013", "9014"):
            assert rs[b].state is RecordState.NEEDS_REVIEW


# ── invalid / edge-case inputs ────────────────────────────────────────────────
class TestInvalidRecords:
    def test_totally_empty_incoming_is_new_not_crash(self):
        cls, *_ = _classify(_mk_inc(), [_mk_master(first_name="A", last_name="B")])
        assert cls is Classification.NEW

    def test_truncated_phone_is_not_evidence(self):
        mas = _mk_master(first_name="Pat", last_name="Short", phone="+353871234567")
        inc = _mk_inc(first_name="Pat", last_name="Short", phone="35387")   # truncated export
        cls, rec, conf, mb, diffs, m, reason = _classify(inc, [mas])
        assert "phone" not in mb
        pd = next(d for d in diffs if d.field == "phone")
        assert not pd.significant   # truncation is never a real change

    def test_unrecognised_csv_raises_valueerror(self):
        from reconciliation.repository import load_upload
        with pytest.raises(ValueError):
            load_upload("Wrong,Header\n1,2\n")
