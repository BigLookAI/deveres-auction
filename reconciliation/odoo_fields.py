"""
deVeres Auction — Reconciliation · Odoo field metadata (Phase 4, Priority 2)
=============================================================================

Metadata-aware synchronisation: the engine must not assume every Odoo field
is plain text. This module reads `fields_get` for res.partner and turns it
into a typed schema the reconciliation and push layers consult:

    field type (char/text/integer/float/boolean/date/datetime/selection/
    many2one/many2many/one2many/html), editability (readonly), required,
    selection values, and — for the relational dropdowns the imports actually
    hit (state_id/county, country_id) — the full list of valid values.

The schema is cached (default 10 minutes) and refreshed together with the
master. When Odoo is not configured (offline/CSV mode) a static Odoo-19
snapshot keeps the validation layer meaningful: canonical field types are
known, and valid county values are derived from the master records instead.

Canonical-field mapping: the reconciliation engine reasons in canonical
fields (fieldmap.py); CANONICAL_TO_ODOO names each one's Odoo home so the
validator can look up the right metadata for an incoming value.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("reconcile.odoo")

CACHE_TTL_S = 600

# canonical engine field → the res.partner field it lands in
CANONICAL_TO_ODOO = {
    "first_name": "name", "last_name": "name", "company": "name",
    "email": "email", "phone": "phone", "mobile": "phone",
    "address1": "street", "address2": "street2",
    "town": "city", "postcode": "zip",
    "county": "state_id", "country": "country_id",
    "notes": "comment",
}

PARTNER_META_FIELDS = [
    "name", "email", "phone", "street", "street2", "city", "zip",
    "state_id", "country_id", "comment", "category_id", "ref",
    "is_company", "type", "active", "parent_id",
]

# Offline fallback: the Odoo 19 res.partner shape, verified live 6-Jul-2026
# (field-editability report). Used when ODOO_URL is not configured so the
# validation layer still knows counties are a dropdown, not free text.
STATIC_ODOO19_PARTNER = {
    "name":       {"type": "char",      "required": True,  "readonly": False},
    "email":      {"type": "char",      "required": False, "readonly": False},
    "phone":      {"type": "char",      "required": False, "readonly": False},
    "street":     {"type": "char",      "required": False, "readonly": False},
    "street2":    {"type": "char",      "required": False, "readonly": False},
    "city":       {"type": "char",      "required": False, "readonly": False},
    "zip":        {"type": "char",      "required": False, "readonly": False},
    "state_id":   {"type": "many2one",  "required": False, "readonly": False,
                   "relation": "res.country.state"},
    "country_id": {"type": "many2one",  "required": False, "readonly": False,
                   "relation": "res.country"},
    "comment":    {"type": "html",      "required": False, "readonly": False},
    "category_id": {"type": "many2many", "required": False, "readonly": False,
                    "relation": "res.partner.category"},
    "ref":        {"type": "char",      "required": False, "readonly": False},
    "is_company": {"type": "boolean",   "required": False, "readonly": False},
    "type":       {"type": "selection", "required": False, "readonly": False,
                   "selection": [["contact", "Contact"], ["invoice", "Invoice Address"],
                                 ["delivery", "Delivery Address"], ["other", "Other Address"]]},
    "active":     {"type": "boolean",   "required": False, "readonly": False},
    "parent_id":  {"type": "many2one",  "required": False, "readonly": False,
                   "relation": "res.partner"},
}


class OdooFieldSchema:
    """Typed res.partner schema + valid values for the relational dropdowns."""

    def __init__(self, fields: dict, states: list[dict], countries: list[dict],
                 source: str):
        self.fields = fields            # odoo field → metadata dict
        self.states = states            # [{id, name, code, country}] — counties
        self.countries = countries      # [{id, name, code}]
        self.source = source            # "odoo" | "static"
        self.loaded_at = time.time()

    # ── lookups the validator uses ────────────────────────────────────────────
    def field_meta(self, canonical_field: str) -> dict | None:
        odoo_field = CANONICAL_TO_ODOO.get(canonical_field)
        return self.fields.get(odoo_field) if odoo_field else None

    def field_type(self, canonical_field: str) -> str:
        meta = self.field_meta(canonical_field)
        return (meta or {}).get("type", "char")

    def state_names(self) -> list[str]:
        return [s["name"] for s in self.states]

    def country_names(self) -> list[str]:
        return [c["name"] for c in self.countries] + \
               [c["code"] for c in self.countries if c.get("code")]

    def to_dict(self) -> dict:
        return {"source": self.source,
                "loaded_at": self.loaded_at,
                "fields": self.fields,
                "counties": len(self.states),
                "countries": len(self.countries)}


def _clean_meta(raw: dict) -> dict:
    keep = ("type", "string", "required", "readonly", "relation", "selection",
            "help")
    return {k: raw[k] for k in keep if k in raw}


def fetch_schema(client=None) -> OdooFieldSchema:
    """Live schema from Odoo: fields_get + the state/country value lists."""
    if client is None:
        from pipeline.odoo_client import OdooClient
        client = OdooClient()
    t0 = time.perf_counter()
    raw = client._execute("res.partner", "fields_get", PARTNER_META_FIELDS,
                          attributes=["type", "string", "required", "readonly",
                                      "relation", "selection", "help"])
    fields = {f: _clean_meta(m) for f, m in raw.items()}
    states = client._execute(
        "res.country.state", "search_read", [],
        fields=["id", "name", "code", "country_id"], limit=5000)
    countries = client._execute(
        "res.country", "search_read", [],
        fields=["id", "name", "code"], limit=500)
    states = [{"id": s["id"], "name": s["name"], "code": s.get("code", ""),
               "country": (s.get("country_id") or [None, ""])[1]} for s in states]
    countries = [{"id": c["id"], "name": c["name"], "code": c.get("code", "")}
                 for c in countries]
    log.info("odoo schema: %d fields, %d states, %d countries in %.0fms",
             len(fields), len(states), len(countries),
             (time.perf_counter() - t0) * 1000)
    return OdooFieldSchema(fields, states, countries, source="odoo")


# Odoo base ships res.country.state rows for Ireland's 26 counties — the
# offline fallback must carry the same vocabulary, otherwise valid counties
# that happen to be absent from the master would false-positive as invalid.
IE_COUNTIES = [
    "Carlow", "Cavan", "Clare", "Cork", "Donegal", "Dublin", "Galway",
    "Kerry", "Kildare", "Kilkenny", "Laois", "Leitrim", "Limerick",
    "Longford", "Louth", "Mayo", "Meath", "Monaghan", "Offaly", "Roscommon",
    "Sligo", "Tipperary", "Waterford", "Westmeath", "Wexford", "Wicklow",
]


def static_schema(master_records: list[dict] | None = None) -> OdooFieldSchema:
    """Offline schema: static Odoo-19 field types; county vocabulary = the
    full Irish county list (what Odoo ships) plus anything extra seen in the
    master, so real-world values never false-positive."""
    states, countries = [], []
    seen_s, seen_c = set(), set()
    for c in IE_COUNTIES:
        seen_s.add(c.lower())
        states.append({"id": None, "name": c, "code": "", "country": "Ireland"})
    seen_c.add("ireland")
    countries.append({"id": None, "name": "Ireland", "code": "IE"})
    for m in master_records or []:
        c = (m.get("county") or "").strip()
        if c and c.lower() not in seen_s:
            seen_s.add(c.lower())
            states.append({"id": None, "name": c, "code": "", "country": ""})
        n = (m.get("country") or "").strip()
        if n and n.lower() not in seen_c:
            seen_c.add(n.lower())
            countries.append({"id": None, "name": n, "code": ""})
    return OdooFieldSchema(dict(STATIC_ODOO19_PARTNER), states, countries,
                           source="static")


# ── module-level cache ────────────────────────────────────────────────────────
_cached: OdooFieldSchema | None = None


def get_schema(master_records: list[dict] | None = None,
               force: bool = False) -> OdooFieldSchema:
    """Cached schema. Odoo-backed when configured; static+master otherwise.
    A live-fetch failure degrades to the static schema (loudly logged) —
    validation must never take the app down."""
    global _cached
    import os
    if (not force and _cached is not None
            and time.time() - _cached.loaded_at < CACHE_TTL_S):
        return _cached
    if os.environ.get("ODOO_URL"):
        try:
            _cached = fetch_schema()
            return _cached
        except Exception as exc:                          # noqa: BLE001
            log.error("odoo schema fetch failed (%s) — using the static "
                      "Odoo-19 schema", exc)
    _cached = static_schema(master_records)
    return _cached


def invalidate_cache() -> None:
    global _cached
    _cached = None
