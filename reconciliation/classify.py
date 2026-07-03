"""
deVeres Auction — Reconciliation · Classifier
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
# county/country included per the 2-Jul meeting (the Wickie→Wicklow case:
# county typos must surface for review, and country completions are welcome).
SIGNIFICANT_FIELDS = {"email", "phone", "address1", "address2", "town",
                      "county", "country", "postcode", "company"}

# Per-field normaliser used to decide equivalence.
def _norm(field: str, value: str) -> str:
    if field == "email":    return N.normalize_email(value)
    if field == "phone":    return N.phone_key(value) or N.normalize_phone(value)
    if field == "postcode": return N.normalize_postcode(value)
    if field == "country":  return N.normalize_country(value)
    if field == "name":     return N.name_key(value)
    if field == "county":   return N.county_key(value)
    if field in ("address1", "address2", "town"): return N.normalize_address(value)
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


# Fields that together form the master's "address block". Odoo masters store
# concatenations (the SOR import filed "address2, address3, county" into
# street2), and the De Veres CSV master misfiles values across these columns —
# so per-field comparison must know the whole block.
_ADDRESS_FAMILY = ("address1", "address2", "address3", "town", "county")


def _address_block_tokens(mas: dict) -> set[str]:
    toks = set(N.normalize_address(
        *[mas.get(f, "") for f in _ADDRESS_FAMILY if f != "county"]).split())
    toks |= set(N.county_key(mas.get("county", "")).split())
    return toks


def diff_fields(inc: dict, mas: dict) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    mas_addr_tokens = _address_block_tokens(mas)
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
        if field in _ADDRESS_FAMILY and ino and cur != ino:
            # The incoming value may already live in the master, filed in a
            # DIFFERENT address column (Odoo masters concatenate address2/3 +
            # county into street2; the CSV master misfiles counties into town).
            # If every incoming token is already present in the master's
            # combined address block, nothing new is being said — EQUIVALENT,
            # never an update. (A genuinely new town/county/street still diffs
            # normally: its tokens are absent from the block.)
            ino_tokens = set((_norm(field, ino) or "").split())
            if ino_tokens and ino_tokens <= mas_addr_tokens:
                diffs.append(FieldDiff(field, label, cur, ino,
                                       DiffStatus.EQUIVALENT, False))
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


# ── Manual-review (POSSIBLE_DUPLICATE) rules — explicit and documented ────────
# A record lands in MANUAL REVIEW when a master candidate exists but the match
# is not safe enough to update automatically. Exactly three rules fire it:
#
#   R1 UNCERTAIN_SCORE   score in [0.55, 0.72) and NO exact email/phone match.
#                        (An exact email/phone floors the score at 0.90, so this
#                        band is only reachable on name/address evidence.)
#   R2 CONFLICT_NO_ID    score ≥ 0.72 but NO exact email/phone match AND at
#                        least one significant field CHANGED (both sides have a
#                        value and they differ). Same name + different details
#                        may be a DIFFERENT PERSON — a human must decide.
#   R3 NAME_ONLY_ADDS    score ≥ 0.72, matched on name alone (no email, phone
#                        or address agreement) and the incoming row wants to add
#                        significant new info. Attaching contact details to a
#                        namesake is how wrong-person merges happen — review it.
#
#   R4 ID_NAME_CONFLICT  exact email/phone match but the NAMES clearly disagree
#                        (similarity < 0.5 with both present). Shared household
#                        phone, spouse's email, or corrupted seed data — writing
#                        one person's details onto the other must be a human
#                        call. (Found live 3-Jul: incoming 'Mark Sloan' updating
#                        master 'Sam Greene' via a shared phone + address.)
#
# With an exact email or phone match R1–R3 never fire: strong-ID matches go
# straight to UPDATE (significant diffs) or RETAIN (formatting only) — unless
# R4's name conflict flags them.

def classify(inc: dict, cand: Candidate | None):
    """Return (Classification, Recommendation, confidence, matched_by, diffs,
    master, review_reason)."""
    # ── No/low candidate → NEW ────────────────────────────────────────────────
    if cand is None or cand.score < REVIEW_FLOOR:
        # A NEW client still gets a field-by-field report: every populated
        # incoming field diffed against an empty master, so the review drawer
        # shows exactly what will be created (an empty diff list left the
        # Incoming column blank for new clients).
        return (Classification.NEW, Recommendation.ADD,
                cand.score if cand else 0.0, [], diff_fields(inc, {}), {}, "")

    diffs = diff_fields(inc, cand.master)
    significant = [d for d in diffs if d.significant and d.status in (DiffStatus.CHANGED, DiffStatus.NEW_INFO)]
    conflicting = [d for d in significant if d.status == DiffStatus.CHANGED]

    strong = ("email" in cand.matched_by) or ("phone" in cand.matched_by)

    def review(reason: str):
        return (Classification.POSSIBLE_DUPLICATE, Recommendation.MANUAL_REVIEW,
                cand.score, cand.matched_by, diffs, cand.master, reason)

    if strong and significant:
        # R4 — the identifier says "same person", the name says otherwise.
        name_sim = cand.field_sims.get("name")
        if name_sim is not None and name_sim < 0.5:
            return review("R4 ID_NAME_CONFLICT: exact "
                          f"{'/'.join(f for f in ('email', 'phone') if f in cand.matched_by)} "
                          f"match, but the names disagree (similarity {name_sim:.0%}) — "
                          "possibly a shared household contact or a different person; "
                          "confirm before updating.")

    if not strong:
        # R1 — uncertain score band without a strong identifier
        if cand.score < MATCH_THRESHOLD:
            return review("R1 UNCERTAIN_SCORE: confidence "
                          f"{cand.score:.0%} is below the {MATCH_THRESHOLD:.0%} match "
                          "threshold and no exact email/phone match exists.")
        # R2 — same name but conflicting details: possibly a different person
        if conflicting:
            return review("R2 CONFLICT_NO_ID: no exact email/phone match and "
                          f"{len(conflicting)} field(s) conflict "
                          f"({', '.join(d.label for d in conflicting)}) — this could "
                          "be a different person with the same name.")
        # R3 — name-only agreement trying to add significant new info
        if significant and not ("address" in cand.matched_by):
            return review("R3 NAME_ONLY_ADDS: matched on name alone; adding "
                          f"{', '.join(d.label for d in significant)} to a possible "
                          "namesake needs human confirmation.")

    # ── Confident match → UPDATE if substantive change, else RETAIN ───────────
    if significant:
        return (Classification.UPDATE, Recommendation.UPDATE_RECORD,
                cand.score, cand.matched_by, diffs, cand.master, "")
    return (Classification.RETAIN, Recommendation.KEEP_EXISTING,
            cand.score, cand.matched_by, diffs, cand.master, "")


def default_action(classification: Classification) -> Action:
    return {
        Classification.NEW:                Action.ADD,
        Classification.UPDATE:             Action.UPDATE,
        Classification.RETAIN:             Action.IGNORE,
        Classification.POSSIBLE_DUPLICATE: Action.MANUAL_REVIEW,
    }[classification]
