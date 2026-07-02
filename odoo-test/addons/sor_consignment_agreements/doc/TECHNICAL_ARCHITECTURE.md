# SOR Consignment Agreements — Technical Architecture

## 1. Overview

`sor_consignment_agreements` is a Level 1 bridge module that activates automatically when both `sor_legal_agreement` and `sor_tracking` are installed. It connects the legal agreement lifecycle to the physical movement infrastructure, enabling pre-signing intake and dispatch pickings that are fixed in scope at countersigning time.

**Dependency diagram:**

```
sor_legal_agreement          sor_tracking
        \                        /
         \                      /
          sor_consignment_agreements   ← this module (auto_install)
```

---

## 2. Module pattern

| Manifest flag | Value | Rationale |
|---------------|-------|-----------|
| `auto_install` | `True` | Activates at the intersection of both parents — no user action required |
| `application` | `False` | Not a top-level app — technical bridge only |
| `category` | `'Hidden/Technical'` | Excluded from business category listings in the Apps menu |
| `depends` | `['sor_legal_agreement', 'sor_tracking']` | Both parents required — neither alone is sufficient |

No `post_init_hook` or `uninstall_hook` — this bridge adds fields and views only; no provisioning or suppression is required.

---

## 3. Architecture decisions

**Pre-signing picking creation (not post-signing):** Intake and dispatch pickings are created in Draft or Pending Signature state, before the agreement is countersigned. This ensures the physical movement scope is fixed and visible on the signed PDF. The guard (`state not in ('draft', 'pending_signature')`) enforces this — it is the inverse of `_check_can_trigger_movement`, which enforces Active state and must not be called here.

**Explicit MVI/MVO picking type lookup:** The Partners/External pool location has `usage='internal'`. Odoo's `_sor_infer_picking_type_id` method classifies a picking as Receipt (MVI) only when `src.usage in ('supplier', 'customer')`. Using the pool as source with inference produces an Internal Transfer (MVT), not a Receipt. Both `action_receive_artwork` and `action_release_artwork` explicitly search `stock.picking.type` by `code` to avoid this.

**`_get_partner_location` as an override point:** The Level 1 default always returns the Partners/External pool. The method accepts a `direction` argument for forward compatibility with the Level 3 bridge (`sor_consignment_agreements_locations_external`), which will override it to check for a contact-linked external location before falling back to the pool.

**`sor_compound_status` is `store=False`:** The compound status is a display-only indicator. It does not represent a formal lifecycle state — the base `state` field remains `active`. Storing it would require either a stored trigger (expensive) or a cron. Instead, `stock.picking._action_done` is overridden to invalidate the field on the source In agreement after a release picking is confirmed, causing recomputation on next read. The `@api.depends('agreement_type', 'state')` declaration is intentionally minimal — the invalidation hook is the authoritative trigger.

**Intermediate lifecycle states deferred:** States `partial_return`, `returned`, `sold`, `expired` are declared in the `statusbar_visible` attribute for future bridge compatibility but are not implemented here. See Sprint Findings A05 for the rationale (business-model bridges own these transitions).

---

## 4. Models

### `sor.agreement` (extends)

| Field / Method | Type | Notes |
|----------------|------|-------|
| `agreement_type` | Selection (add) | `consignment_in`, `consignment_out`. `ondelete='set null'` — base field has no default; `set default` is invalid without a default declared |
| `source_consignment_id` | Many2one → `sor.agreement` | Domain filtered to `consignment_in`. Optional — standalone Out agreements are valid |
| `picking_count` | Integer, computed, `store=False` | `len(picking_ids)` — drives stat button; declared `store=False` because it reads a One2many count, not company context |
| `move_ids` | One2many (computed), `store=False` | `picking_ids.move_ids` — flat display list for Movements tab; arch declaration `<field name="move_ids" invisible="1"/>` required before the notebook (Odoo 19 `FormArchParser` resolves field types at parse time) |
| `sor_compound_status` | Char, computed, `store=False` | Returns `'Active \| Consigned out'` or `False`; declared `store=False` because it reads related agreement state at call time |
| `_get_partner_location` | Method | Override point for Level 3 bridge; default returns Partners/External pool |
| `action_view_movements` | Method | Server-side filtered stat button action — domain includes `self.id` |
| `action_receive_artwork` | Method | MVI picking creation; guard: `draft` / `pending_signature` only |
| `action_link_existing_intake` | Method | Opens filtered receipt-pickings window; same guard |
| `action_release_artwork` | Method | MVO picking creation; same guard |
| `action_link_existing_release` | Method | Opens filtered delivery-pickings window; same guard |

### `stock.picking` (extends)

| Method | Notes |
|--------|-------|
| `action_open_picking_modal` | Modal (`target: 'new'`) opener for the Movements tab "Open ↗" button — added in Story 02; shared by Stories 04 and 05 |
| `_action_done` (override) | Post-validation hook: for each picking linked to a `consignment_out` agreement with a `source_consignment_id`, invalidates `sor_compound_status` on the source In agreement |

---

## 5. Views

**`views/sor_agreement_views.xml`** — single `ir.ui.view` record inheriting `sor_legal_agreement.view_sor_agreement_form`:

| XPath target | Change | Notes |
|---|---|---|
| `//header` inside | Add action buttons (Receive Artwork, Link Existing Intake, Release Artwork, Link Existing Release) | Visibility gated on `agreement_type` + `state` |
| `//field[@name='state']` after | `sor_compound_status` field | Renders below statusbar; hidden when falsy |
| `//field[@name='state'][@widget='statusbar']` attributes | `statusbar_visible` | Extends with future consignment states for forward compatibility |
| `//div[@class='oe_title']` before | `oe_button_box` with Movements stat button | Odoo 19 form compiler extracts button box to control panel — must be before sheet content |
| `//notebook` before | `<field name="move_ids" invisible="1"/>` | Arch type declaration — required for `FormArchParser` to resolve `move_ids` type |
| `//field[@name='primary_partner_id']` after | `source_consignment_id` | Invisible on non-consignment_out types |
| `//page[@name='lines']` attributes | `invisible` expression | Hides base Lines tab for consignment types |
| `//page[@name='lines']` after | Movements tab | Two sections: Linked Movements (`picking_ids`) + Product Lines (`move_ids`) |

**Report:** `report/consignment_agreement_report.xml` — extends `sor_legal_agreement` PDF template with:
- Source Consignment reference (Consignment Out only)
- Product Lines table (artwork items on linked pickings)

---

## 6. Module file structure

```
sor_consignment_agreements/
├── __manifest__.py              — bridge flags, depends, data list
├── __init__.py                  — imports models subpackage
├── models/
│   ├── __init__.py              — imports sor_agreement, stock_picking
│   ├── sor_agreement.py         — all sor.agreement extensions (fields, methods)
│   └── stock_picking.py         — action_open_picking_modal + _action_done override
├── views/
│   └── sor_agreement_views.xml  — single inherited view with all XPath patches
├── report/
│   └── consignment_agreement_report.xml  — PDF template extension
├── security/
│   └── ir.model.access.csv      — no new models; empty except header
├── i18n/
│   └── sor_consignment_agreements.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_consignment_agreements.py
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## 7. Critical files

| File | Purpose |
|------|---------|
| `models/sor_agreement.py` | All bridge logic — picking creation, location resolution, compound status computation |
| `models/stock_picking.py` | `_action_done` override that triggers compound status invalidation |
| `views/sor_agreement_views.xml` | All UI additions — buttons, tabs, stat button, status display |
| `report/consignment_agreement_report.xml` | PDF additions — source consignment reference and product lines |

---

## 8. Composability boundary

| Installed combination | Behaviour |
|-----------------------|-----------|
| `sor_legal_agreement` only | Module absent; no consignment types; Base Agreement works normally |
| `sor_tracking` only | Module absent; movement infrastructure works normally; no agreement types |
| Both parents | Bridge active; Consignment In + Out available; pre-signing movements; compound status |
| + `sor_tracking_artwork` | Serial tracking column in Movements tab populated automatically (no bridge code needed — `sor_tracking_artwork` handles this on all `stock.move` records) |
| + `sor_consignment_agreements_locations_external` (planned) | `_get_partner_location` returns contact-linked external location when available |
| + business-model bridge (planned) | Intermediate lifecycle states available via `selection_add` on `state` |

---

## 9. Special concerns

**`ondelete='set null'` on `agreement_type` selection_add:** The base `agreement_type` field has no `default` declared. Using `ondelete='set default'` (the intuitive choice) raises `AssertionError` at registry load time when no default is defined. Use `'set null'` — records revert to `None` on module uninstall.

**`move_ids` arch declaration:** Odoo 19's `FormArchParser` resolves field types from the combined arch at parse time. `move_ids` is a computed `One2many` (`store=False`) used in a list widget. Without `<field name="move_ids" invisible="1"/>` declared before the `<notebook>`, the OWL widget crashes with `Cannot read properties of undefined (reading 'type')` at runtime.

**`oe_button_box` placement in Odoo 19:** Odoo 19's form compiler does not render `oe_button_box` inside the sheet. It is extracted by `compileSheet` and moved to the `layout-actions` slot in the control panel (breadcrumb bar). The XPath inserts before `//div[@class='oe_title']` — the `@class` selector produces an "Error-prone use of @class" warning in logs but works correctly. The button box does not appear inside dialogs (`t-if="!__comp__.env.inDialog"`) — this is expected Odoo 19 behaviour.

**Partners/External `usage='internal'`:** All consignment location resolution bypasses `_sor_infer_picking_type_id`. Both `action_receive_artwork` and `action_release_artwork` use explicit `code=` lookup on `stock.picking.type`. This is a permanent constraint, not a workaround.

**`_action_done` vs `action_cancel` hooks:** In Odoo 19, `button_validate()` calls `_action_done()` on the picking. `action_cancel()` calls `_action_cancel()` on the moves, not on the picking. The compound status invalidation override uses `_action_done` (correct). Any future cancellation hook must override `action_cancel` on `stock.picking`, not `_action_cancel`.

---

## 10. Running the tests

```bash
# Sync worktree changes to main addons first
bash /tmp/sor_sync_module.sh

# Run tests against odoo_testlab
docker exec odoo-app python3 /app/odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  --http-port=8072 \
  -d odoo_testlab \
  -u sor_consignment_agreements \
  --test-enable \
  --test-tags sor_consignment_agreements \
  --stop-after-init

# Check results
docker exec odoo-app grep "sor_consignment_agreements.*tests" /var/log/odoo/odoo-server.log | tail -5
```

**Expected:** `sor_consignment_agreements: 30 tests` — no FAIL or ERROR lines.

---

## 11. Story reference

- [Story 01 — Consignment Agreement Model](../../../../.backlog/current/Consignment%20Agreements/stories/01_Consignment-Agreement-Model.md)
- [Story 02 — Agreement Form & Movements Tab](../../../../.backlog/current/Consignment%20Agreements/stories/02_Agreement-Form-and-Artwork-Table.md)
- [Story 03 — Agreement PDF](../../../../.backlog/current/Consignment%20Agreements/stories/03_Agreement-PDF.md)
- [Story 04 — Consignment In Lifecycle](../../../../.backlog/current/Consignment%20Agreements/stories/04_Consignment-In-Lifecycle.md)
- [Story 05 — Consignment Out](../../../../.backlog/current/Consignment%20Agreements/stories/05_Consignment-Out.md)
