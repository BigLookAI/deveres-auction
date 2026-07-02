# Technical Architecture: sor_consignment_auction

## Overview

`sor_consignment_auction` is a **bridge module** that activates the consignor auto-population pipeline when `sor_consignment_agreements` and `sor_auction_documents` are both installed:

```
sor_consignment_agreements    sor_auction_documents
          \                          /
           \                        /
        sor_consignment_auction   (auto_install=True)
```

The bridge has no new models. It extends `sor.lot` with a traversal method and auto-population hook, extends `sor.event` with batch resolution and overrides of the document generation actions, and patches the lot form view to replace the editable `consignor_id` field with a system-managed layout.

---

## Module Pattern

**Manifest flags:**

```python
'category': 'Hidden/Technical',
'depends': ['sor_consignment_agreements', 'sor_auction_documents'],
'auto_install': True,
'application': False,
```

- `auto_install: True` — Odoo installs the bridge automatically when both parents are present. The consignor resolution pipeline activates silently for auction houses that also use the consignment agreements module.
- `application: False` — Not a standalone App.
- `category: 'Hidden/Technical'` — Excluded from business category listings.
- No `summary` — bridge convention; no marketing metadata.

---

## Architecture Decisions

### Serial-based traversal (not product_id)

The traversal resolves `sor.lot.product_id` → `stock.lot` (serial) → `stock.picking` → `sor.agreement`. Using the serial as the pivot rather than matching `product_id` directly is intentional:

- Auction lots typically represent physically unique objects. Multiple distinct objects may share the same `product.template` (e.g. "Large Bronze, Edition 3/5" — five distinct serial numbers, same template).
- `stock.lot` serial records are the universal identifier for unique tracked objects in the Odoo inventory layer.
- `sor_tracking` (a hard dependency of `sor_consignment_agreements`) ensures serial tracking exists in any context where this bridge is installed.

### All picking states searched (not only done)

The `stock.picking` search includes all states (`sor_movement_state` not filtered). Intake movements are created as draft/queued as part of the consignment workflow, before physical arrival. By the time a lot is catalogued, the corresponding movement may be queued but not yet confirmed. Restricting to `state = 'done'` would leave `consignor_id` blank for lots catalogued before physical intake is confirmed — a common pre-auction scenario.

### Two-step picking search for diagnostic distinction

```python
# Step 1: any incoming picking for the serial
picking_any = self.env['stock.picking'].search([
    ('picking_type_id.code', '=', 'incoming'),
    ('move_line_ids.lot_id', '=', stock_lot.id),
    ('company_id', '=', self.company_id.id),
], limit=1)
if not picking_any:
    return False, 'missing_movement'

# Step 2: picking with consignment_in agreement
picking = self.env['stock.picking'].search([
    ('picking_type_id.code', '=', 'incoming'),
    ('agreement_id', '!=', False),
    ('agreement_id.agreement_type', '=', 'consignment_in'),
    ('move_line_ids.lot_id', '=', stock_lot.id),
    ('company_id', '=', self.company_id.id),
], order='date_done desc, id desc', limit=1)
if not picking:
    return False, 'missing_consignment'
```

If Step 1 found a picking but Step 2 did not, the distinction is `missing_consignment` (incoming movement exists, but not linked to a consignment agreement). A single-step search returning no result cannot distinguish "no movement at all" from "movement exists but wrong type." Both diagnostics lead to different staff actions — separate queries preserve the information.

### agreement.primary_partner_id (not picking.partner_id) as consignor

`picking.partner_id` is the delivery contact — it may be a courier, a studio assistant, or a third party. For retroactively-attached movements (picking created then agreement linked later), `partner_id` is often not set from the agreement. `agreement_id.primary_partner_id` is always the contractual counterparty and the correct consignor for financial documents.

### View inheritance from sor_auction_documents view (not base lot view)

`views/sor_lot_consignment_auction_views.xml` inherits from `sor_auction_documents.view_sor_lot_form_inherit_auction_docs` (the intermediate view), not from the base `sor_lotting.sor_lot_view_form`. This is intentional:

- The XPath target is `//field[@name='consignor_id']` — this element is injected by `sor_auction_documents`, not present in the base view.
- Inheriting from the base view and then targeting the bridge-injected field creates a dependency ordering problem; Odoo resolves view inheritance by `inherit_id` chain, so inheriting from the immediate parent view that owns the target element is correct.

### REASON_LABELS at module level — plain strings only

The `REASON_LABELS` dict is defined at module level (outside any class) in `sor_lot_consignment_auction.py` and imported by `sor_event_consignment_auction.py`. Module-level dict values must be plain Python strings — not `_()` wrappers. `_()` at module level evaluates at import time with no user context and raises `MissingError`. Translation is applied inside method bodies at the point of string usage: `_(REASON_LABELS.get(reason, ...))`.

---

## Models

All changes are via `_inherit` — no new models.

### sor_lot_consignment_auction.py — extends sor.lot

| Element | Description |
|---------|-------------|
| `REASON_LABELS` dict | Module-level constant mapping reason codes to user-facing diagnostic strings. Imported by the event model file. |
| `_resolve_consignor()` | Core traversal method. See two-step search design above. |
| `action_fetch_consignor()` | On-demand resolution. Returns `False` on success (bus notification sent separately); returns `display_notification` action dict on failure. |
| `create()` override | `@api.model_create_multi`. Calls `super()` first, then iterates the created lots. For each lot without `consignor_id` and with a `product_id`, calls `_resolve_consignor()` and sets `consignor_id` if a partner is returned. |

### sor_event_consignment_auction.py — extends sor.event

| Element | Description |
|---------|-------------|
| `_resolve_consignors_for_event()` | Batch traversal. Iterates `self.lot_ids`; skips lots with `consignor_id` set; calls `lot._resolve_consignor()` on the rest. Returns `{'resolved': rs, 'unresolved': [{lot, ref, reason}]}`. |
| `_format_consignor_diagnostic(unresolved)` | Formats the unresolved list as a multi-line string for inclusion in bus notifications. |
| `_notify_consignor_gaps(unresolved)` | `bus.bus._sendone` — sticky warning notification listing unresolvable lots. No-op when `unresolved` is empty. |
| `action_generate_pre_sale_advices()` | Calls `_resolve_consignors_for_event()` → `_notify_consignor_gaps()` → `super()`. |
| `action_generate_post_sale_advices()` | Same pattern. |
| `action_generate_vendor_settlements()` | Same pattern. |

---

## Views

### `views/sor_lot_consignment_auction_views.xml`

One inheritance record on `sor.lot`:

**Form view** (`view_sor_lot_form_inherit_consignment_auction`) — inherits `sor_auction_documents.view_sor_lot_form_inherit_auction_docs`. XPath replaces `//field[@name='consignor_id']` with a `label + div.d-flex` layout:

- `consignor_id` — `readonly="1"`, `nolabel="1"`, `options="{'no_open': True}"`
- "Fetch Consignor" button (`btn-secondary btn-sm`) — visible only when `consignor_id == False` and state in `('draft', 'catalogued')`
- Refresh icon button (`fa-refresh`, `btn-link`) — visible only when `consignor_id != False` and state in `('draft', 'catalogued')`

Both buttons call `action_fetch_consignor`. The dual-button pattern (text button for empty state, icon for non-empty) is per the SOR Design Patterns §1 (modal dialog for related record opens — inline button alongside Many2one). The text "Fetch Consignor" was noted as a Finding 1 in Show & Tell (preference for icon-only); the UAT triage deferred this to a future iteration.

---

## Module File Structure

```
sor_consignment_auction/
├── __manifest__.py          — depends on sor_consignment_agreements, sor_auction_documents; auto_install=True
├── __init__.py              — imports models
├── models/
│   ├── __init__.py
│   ├── sor_lot_consignment_auction.py    — REASON_LABELS, _resolve_consignor, action_fetch_consignor, create()
│   └── sor_event_consignment_auction.py  — batch resolution, gap notification, action overrides
├── views/
│   └── sor_lot_consignment_auction_views.xml   — consignor_id readonly + Fetch/Refresh buttons
├── security/
│   └── ir.model.access.csv              — no new models; header row only
├── i18n/
│   └── sor_consignment_auction.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_consignment_auction.py
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/sor_lot_consignment_auction.py` | Core traversal (`_resolve_consignor`) and all three entry points (at-create, fetch button, callable by batch) |
| `models/sor_event_consignment_auction.py` | Batch wrapper and document action overrides; imports `REASON_LABELS` for diagnostic formatting |
| `views/sor_lot_consignment_auction_views.xml` | Replaces editable consignor field (from `sor_auction_documents`) with readonly+buttons layout; inherits from `sor_auction_documents` view (not base) |

---

## Composability Boundary

| Installation | Lot form | Auto-populate | Fetch button | Batch on generation |
|-------------|---------|---------------|-------------|---------------------|
| `sor_auction_documents` only | Editable `consignor_id` field | No | No | No |
| + `sor_consignment_auction` | Readonly `consignor_id` + Fetch/Refresh buttons | Yes | Yes | Yes |

Uninstalling `sor_consignment_auction` restores the editable standalone behaviour — the bridge only adds view patches and method overrides; it does not modify any records owned by its parent modules.

---

## Special Concerns

### product.template vs product.product in serial lookup

`sor.lot.product_id` is `product.template`. `stock.lot.product_id` is `product.product`. The traversal resolves via `self.product_id.product_variant_ids` before searching `stock.lot`. For artworks (unique tracked objects, one variant per template), `product_variant_ids` always returns a single record. Multi-variant products are not a current auction house concern, but the code handles them correctly via `('product_id', 'in', product_variants.ids)`.

### create() override uses `@api.model_create_multi`

The `create()` override follows Odoo 19's required signature for all model create overrides. It calls `super()` first and iterates the returned recordset. Auto-population failures (any reason code) are silently skipped — no exception, no notification. The Fetch Consignor button is the staff-facing mechanism for inspecting failures.

### bus.bus notification in success path of action_fetch_consignor

On successful resolution, `action_fetch_consignor` sends a bus notification via `self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {...})` and returns `False` (not a window action dict). The bus approach was chosen over `display_notification` for the success case because the success state is self-evident from the field populating — a non-sticky notification is sufficient and avoids requiring the user to dismiss it. The failure case uses `display_notification` with `sticky=True` because the diagnostic requires deliberate acknowledgement.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_consignment_auction
```

Note: running `-u sor_consignment_auction` also runs tests from parent modules in the same upgrade run. To isolate, upgrade both parents first (`-u sor_consignment_agreements,sor_auction_documents`) then run the bridge test in a second pass.

---

## Story Reference

- Story 02: `.backlog/current/Auction House Documents Foundation/stories/02_Consignment-Auction-Traversal.md`
- Story 03: `.backlog/current/Auction House Documents Foundation/stories/03_Consignment-Auction-Interactive.md`
