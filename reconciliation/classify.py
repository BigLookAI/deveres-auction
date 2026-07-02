"""
Deviours Auction — Reconciliation · Classifier
==============================================

Turns a (incoming contact, best master candidate, score) into a decision:
NEW · RETAIN · UPDATE · POSSIBLE_DUPLICATE — plus a field-by-field difference
report where formatting-only changes are marked EQUIVALENT (and never trigger
an update), per the meeting rule that the canonical record wins over trivia.
"""
from __future__ import annotations

from . import normalize as N
from .fieldmap import DIFF_FIELDS
from .matching import Candidate
from .models import (
    Action, Classification, DiffStatus, FieldDiff, Recommendation,
)

# Confidence thresholds (tunable).
MATCH_THRESHOLD  = 0.72   # ≥ → treat as the same client (RETAIN or UPDATE)
REVIEW_FLOOR     = 0.55   # [REVIEW_FLOOR, MATCH_THRESHOLD) → POSSIBLE_DUPLICATE
# < REVIEW_FLOOR → NEW

# Fields whose meaningful change constitutes a substantive UPDATE.
SIGNIFICANT_FIELDS = {"email", "phone", "address1", "address2", "town", "postcode", "company"}

# Per-field normaliser used to decide equivalence.
def _norm(field: str, value: str) -> str:
    if field == "email":    return N.normalize_email(value)
    if field == "phone":    return N.phone_key(value) or N.normalize_phone(value)
    if field == "postcode": return N.normalize_postcode(value)
    if field == "country":  return N.normalize_country(value)
    if field == "name":     return N.name_key(value)
    if field in ("address1", "address2", "town", "county"): return N.normalize_address(value)
    if field == "company":  return N.normalize_name(value)
    return N.collapse_ws(value).lower()


def _pair_values(field: str, inc: dict, mas: dict) -> tuple[str, str]:
    if field == "name":
        cur = N.collapse_ws(f"{mas.get('first_name','')} {mas.get('last_name','')}")
        ino = N.collapse_ws(f"{inc.get('first_name','')} {inc.get('last_name','')}")
        return cur, ino
    return N.collapse_ws(mas.get(field, "")), N.collapse_ws(inc.get(field, ""))


def _phone_diff(inc: dict, mas: dict) -> FieldDiff | None:
    """Phone comparison is special: the Blue Cubes export frequently TRUNCATES
    numbers (e.g. '35387'). A truncated/unusable incoming value must never be
    read as a real change — only two fully-usable, differing numbers are a
    significant CHANGED. Master's number may live in telNo OR mobile."""
    inc_raw = N.collapse_ws(inc.get("phone", ""))
    mas_raw = N.collapse_ws(mas.get("phone", "") or mas.get("mobile", ""))
    if not inc_raw and not mas_raw:
        return None
    inc_key = N.phone_key(inc_raw)
    mas_keys = [k for k in (N.phone_key(mas.get("phone", "")),
                            N.phone_key(mas.get("mobile", ""))) if k]
    if not inc_raw:
        status, sig = DiffStatus.MISSING, False
    elif not inc_key:                     # incoming truncated/partial → unreliable
        status, sig = (DiffStatus.EQUIVALENT if mas_raw else DiffStatus.NEW_INFO), False
    elif not mas_keys:
        status, sig = DiffStatus.NEW_INFO, True
    elif inc_key in mas_keys:
        status, sig = DiffStatus.EQUIVALENT, False
    else:
        status, sig = DiffStatus.CHANGED, True
    return FieldDiff("phone", "Phone", mas_raw, inc_raw, status, sig)


def diff_fields(inc: dict, mas: dict) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for field, label in DIFF_FIELDS:
        if field == "phone":
            pd = _phone_diff(inc, mas)
            if pd:
                diffs.append(pd)
            continue
        cur, ino = _pair_values(field, inc, mas)
        if not cur and not ino:
            continue
        # ── Data-quality aware handling for the De Veres master ──────────────
        if field == "postcode" and ino:
            # The correct postcode may be misfiled in the master's town field.
            mas_town = N.collapse_ws(mas.get("town", ""))
            if _norm("postcode", ino) in (_norm("postcode", cur), N.normalize_postcode(mas_town)):
                diffs.append(FieldDiff(field, label, cur or mas_town, ino,
                                       DiffStatus.EQUIVALENT, False))
                continue
        if field == "town" and cur and N.is_eircode(cur) and ino and not N.is_eircode(ino):
            # Master 'town' actually holds an Eircode → it has no real town value;
            # the incoming town is genuinely new information (a correction).
            diffs.append(FieldDiff(field, label, cur, ino, DiffStatus.NEW_INFO, True))
            continue
        if cur == ino:
            status, sig = DiffStatus.UNCHANGED, False
        elif not ino:
            status, sig = DiffStatus.MISSING, False          # incoming blank → never overwrite
        elif not cur:
            status, sig = DiffStatus.NEW_INFO, field in SIGNIFICANT_FIELDS
        elif _norm(field, cur) == _norm(field, ino):
            status, sig = DiffStatus.EQUIVALENT, False        # formatting-only
        else:
            status, sig = DiffStatus.CHANGED, field in SIGNIFICANT_FIELDS
        diffs.append(FieldDiff(field=field, label=label, current=cur,
                               incoming=ino, status=status, significant=sig))
    return diffs


def classify(inc: dict, cand: Candidate | None):
    """Return (Classification, Recommendation, confidence, matched_by, diffs, master)."""
    # ── No/low candidate → NEW ────────────────────────────────────────────────
    if cand is None or cand.score < REVIEW_FLOOR:
        return (Classification.NEW, Recommendation.ADD,
                cand.score if cand else 0.0, [], [], {})

    diffs = diff_fields(inc, cand.master)
    significant = [d for d in diffs if d.significant and d.status in (DiffStatus.CHANGED, DiffStatus.NEW_INFO)]

    # ── Uncertain band → MANUAL REVIEW ────────────────────────────────────────
    strong = ("email" in cand.matched_by) or ("phone" in cand.matched_by)
    if cand.score < MATCH_THRESHOLD and not strong:
        return (Classification.POSSIBLE_DUPLICATE, Recommendation.MANUAL_REVIEW,
                cand.score, cand.matched_by, diffs, cand.master)

    # ── Confident match → UPDATE if substantive change, else RETAIN ───────────
    if significant:
        return (Classification.UPDATE, Recommendation.UPDATE_RECORD,
                cand.score, cand.matched_by, diffs, cand.master)
    return (Classification.RETAIN, Recommendation.KEEP_EXISTING,
            cand.score, cand.matched_by, diffs, cand.master)


def default_action(classification: Classification) -> Action:
    return {
        Classification.NEW:                Action.ADD,
        Classification.UPDATE:             Action.UPDATE,
        Classification.RETAIN:             Action.IGNORE,
        Classification.POSSIBLE_DUPLICATE: Action.MANUAL_REVIEW,
    }[classification]
