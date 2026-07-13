# Contact Field Mapping — Blue Cubes → Reconciliation → Odoo

Verified against the live demo Odoo (Odoo 19 + SOR auction modules) on
2026-07-06. The canonical schema in `reconciliation/fieldmap.py` is the single
source of truth; `reconciliation/odoo_master.py` (pull) and
`reconciliation/odoo_import.py` (push) map it onto `res.partner`.

## Contact fields

| Blue Cubes (buyer export) | Canonical (engine) | Odoo `res.partner` | Direction | Status |
|---|---|---|---|---|
| First Name | `first_name` | `name` (joined "First Last") | pull + push | ✅ |
| Last Name | `last_name` | `name` (joined) | pull + push | ✅ |
| — (sellers: Company) | `company` | `name` when no person name / `is_company` | pull | ✅ (updates: surfaced as unmapped, never silently dropped) |
| Email | `email` | `email` | pull + push | ✅ |
| Phone | `phone` | `phone` | pull + push | ✅ |
| — (sellers/master: Mobile) | `mobile` | *none — Odoo 19 removed `res.partner.mobile`* | push fallback | ✅ mapped to `phone` when phone empty, else kept in `comment` (never lost) |
| Address 1 | `address1` | `street` | pull + push | ✅ |
| Address 2 | `address2` | `street2` | pull + push | ✅ |
| — (master: address3) | `address3` | `street2` (joined ", ") on seed; diff-compared inside the address block | pull | ✅ |
| Town | `town` | `city` | pull + push | ✅ |
| County | `county` | `state_id` (name → id lookup, `Co./County` prefix stripped, N. Ireland alias, trailing punctuation trimmed) | pull (display name) + push (id) | ✅ — unresolved names land in `comment`, flagged for manual set |
| Country | `country` | `country_id` (name or 2-letter code → id) | pull + push | ✅ |
| Postcode | `postcode` | `zip` | pull + push | ✅ |
| Buyer Number | `buyer_number` | `ref` = `BC-<buyer number>` for created contacts | push (create) | ✅ |
| — (master) | `client_ref` | `ref` (fallback `ODOO-<id>` when a partner has no ref) | pull + push resolve | ✅ |
| — | notes (reviewer) | `comment` (audit note: source file, approver, timestamp, ID-check flag, unresolved lookups, overflow mobile) | push | ✅ |
| — | — | `category_id` (Tags) | verified editable; not part of reconciliation | ✅ editable, unmapped by design |

## Lot fields (import preview)

| Blue Cubes (Lot List) | Canonical | Note |
|---|---|---|
| Lot Number / Title / Description / Condition | `lot_number` / `title` / `description` / `condition` | preview only |
| Estimate From / To, Starting Bid, Reserve | `estimate_low/high`, `starting_bid`, `reserve` | preview only |
| Hammer | `hammer` | **forced to 0 on import** (1-Jul meeting rule); export value kept as `hammer_export` for audit |

## Gaps / by-design exclusions

- **Mobile**: no Odoo 19 field — handled by the phone/comment fallback above.
- **Company on updates**: a changed company name is reported on the operation
  (`NOTE unmapped field changes not written`) rather than written, pending a
  decision on how company renames should affect `res.partner` structure.
- **Title (Mr/Ms)**: parsed from the master CSV, not pushed (no reliable Odoo
  mapping; Odoo has a separate `title` many2one with fixed values).
- **County/state convention** (`state_id` by name, country-scoped) still awaits
  Fintan's formal confirmation — the importer's behaviour is safe either way
  (unresolved → comment, nothing guessed).
