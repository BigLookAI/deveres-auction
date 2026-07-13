"""
deVeres Auction — Reconciliation · Incoming-value validation (Phase 4, P3)
===========================================================================

The meeting's Wiki/Wicklow case: County is an Odoo dropdown (state_id); an
incoming value that is not a valid selection must never fail silently. This
layer checks every incoming value against the Odoo field schema
(odoo_fields.OdooFieldSchema) and produces structured issues:

  • blocking issues (invalid dropdown/selection value) — the record is forced
    into Manual Review with a plain-English reason and nearest-match
    suggestions, approval is refused until the value is corrected or cleared,
    and the importer will refuse the field even if something slips through.
  • warnings (suspect email format, unusable phone) — surfaced on the record,
    never blocking (the fields are free text in Odoo).

Comparisons are normalisation-aware (the engine's own normalize helpers), so
"Co. Wicklow", "WICKLOW." and "Wicklow" all validate against Odoo's
"Wicklow" — only genuinely unknown values ("Wickie") are flagged.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field, asdict

from . import normalize as N
from .odoo_fields import OdooFieldSchema

BLOCKING_KINDS = {"invalid_selection"}
SUGGESTION_CUTOFF = 0.5   # 'Wiki'→'Wicklow' = 0.545 — the meeting's own case must suggest
MAX_SUGGESTIONS = 3

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


@dataclass
class ValidationIssue:
    field:      str          # canonical field name (e.g. "county")
    label:      str          # human label (e.g. "County")
    value:      str          # the offending incoming value
    kind:       str          # invalid_selection | suspect_email | unusable_phone
    message:    str          # plain-English explanation
    suggestions: list[str] = field(default_factory=list)
    blocking:   bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _county_candidates(value: str) -> list[str]:
    """Normalised lookup keys for an incoming county (Co./County prefix,
    punctuation) — mirrors the importer's resolution rules."""
    v = value.strip().rstrip(".,;")
    out = [v]
    # dot may be unspaced: the real April export has 'CO.DUBLIN' — but never
    # strip bare 'Co…' words like Cork
    stripped = re.sub(r"^\s*(co\.\s*|co\s+|county\s+)", "", v, flags=re.I).strip()
    if stripped and stripped.lower() != v.lower():
        out.append(stripped)
    # Dublin postal districts ('Dublin 8', 'DUBLIN 6', 'Dublin 6W') → Dublin
    for form in list(out):
        if re.match(r"^dublin\s*\d+\s*w?$", form, flags=re.I):
            out.append("Dublin")
            break
    return out


def _match_in(value_forms: list[str], valid: list[str]) -> bool:
    vset = {x.strip().lower() for x in valid}
    return any(f.strip().lower() in vset for f in value_forms)


def _suggest(value: str, valid: list[str]) -> list[str]:
    """Nearest valid values, best first (difflib over lowered names)."""
    lowered = {v.lower(): v for v in valid}
    hits = difflib.get_close_matches(value.strip().lower(), list(lowered),
                                     n=MAX_SUGGESTIONS, cutoff=SUGGESTION_CUTOFF)
    return [lowered[h] for h in hits]


def validate_incoming(inc: dict, schema: OdooFieldSchema) -> list[ValidationIssue]:
    """All issues for one incoming contact. Empty list = clean."""
    issues: list[ValidationIssue] = []

    # County → res.country.state (dropdown)
    county = (inc.get("county") or "").strip()
    if county and schema.field_type("county") == "many2one":
        valid = schema.state_names()
        if valid and not _match_in(_county_candidates(county), valid):
            sug = _suggest(county, valid)
            issues.append(ValidationIssue(
                "county", "County", county, "invalid_selection",
                f"“{county}” is not a valid County — in Odoo this field is a "
                f"dropdown (res.country.state), and pushing an unknown value "
                f"would silently not apply."
                + (f" Did you mean: {', '.join(sug)}?" if sug else ""),
                suggestions=sug, blocking=True))

    # Country → res.country (dropdown)
    country = (inc.get("country") or "").strip()
    if country and schema.field_type("country") == "many2one":
        valid = schema.country_names()
        if valid and not _match_in([country], valid) \
                and N.normalize_country(country) not in {v.lower() for v in valid}:
            sug = _suggest(country, [c for c in valid if len(c) > 2])
            issues.append(ValidationIssue(
                "country", "Country", country, "invalid_selection",
                f"“{country}” is not a valid Country selection."
                + (f" Did you mean: {', '.join(sug)}?" if sug else ""),
                suggestions=sug, blocking=True))

    # Email format (free text in Odoo — warning only)
    email = (inc.get("email") or "").strip()
    if email and not _EMAIL_RE.match(email):
        issues.append(ValidationIssue(
            "email", "Email", email, "suspect_email",
            f"“{email}” does not look like a valid email address.",
            blocking=False))

    # Phone usability (Blue Cubes truncation — warning only)
    phone = (inc.get("phone") or "").strip()
    if phone and not N.phone_key(phone):
        issues.append(ValidationIssue(
            "phone", "Phone", phone, "unusable_phone",
            f"“{phone}” is too short/damaged to be a usable phone number "
            f"(a known Blue Cubes export truncation) — it will not be pushed.",
            blocking=False))

    return issues


def blocking_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.blocking]


def unresolved_blocking(issues: list[ValidationIssue], edits: dict,
                        schema: OdooFieldSchema) -> list[ValidationIssue]:
    """Blocking issues NOT yet fixed by the reviewer's edits. An edit fixes an
    issue when it clears the field or replaces it with a valid value."""
    out = []
    for i in blocking_issues(issues):
        if i.field in (edits or {}):
            new = (edits[i.field] or "").strip()
            if not new:
                continue                     # cleared → nothing invalid pushed
            valid = (schema.state_names() if i.field == "county"
                     else schema.country_names())
            forms = _county_candidates(new) if i.field == "county" else [new]
            if _match_in(forms, valid):
                continue                     # corrected to a valid selection
        out.append(i)
    return out


def issues_from_dicts(raw: list[dict] | None) -> list[ValidationIssue]:
    return [ValidationIssue(**{k: d.get(k, [] if k == "suggestions" else "")
                               for k in ("field", "label", "value", "kind",
                                         "message", "suggestions", "blocking")})
            for d in (raw or [])]
