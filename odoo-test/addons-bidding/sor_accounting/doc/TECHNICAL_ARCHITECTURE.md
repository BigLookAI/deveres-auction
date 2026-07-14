# SOR Accounting — Technical Architecture

## 1. Overview

`sor_accounting` is a thin infrastructure module. Its two responsibilities are: (1) restrict GL/reporting menus to developer mode via lifecycle hooks, and (2) patch the `account.move` form to remove a POS dependency in the `ReceiptSelector` widget. No models are defined. No data files beyond a single view XML.

---

## 2. Module pattern

```python
'depends': ['account', 'base_setup', 'sor_technical_menu'],
'auto_install': False,
'application': False,
'category': 'Hidden/Technical',
'post_init_hook': 'post_init_hook',
'uninstall_hook': 'uninstall_hook',
```

Not `auto_install` — must be explicitly installed. The hooks ensure GL menus are restricted at install and restored at uninstall.

---

## 3. Architecture decisions

**Hook-based suppression (not data XML):** Menu suppression uses `post_init_hook` / `uninstall_hook` rather than data XML with `<record>` elements. Data XML `active=False` on core records is permanent — it survives module upgrades and uninstall. Hooks are reversible: `uninstall_hook` restores the menus when the module is removed.

**`sor_technical_menu` utilities:** Rather than writing directly to `ir.ui.menu`, the hooks call `set_menu_developer_only(env, xmlid)` and `set_menu_unrestricted(env, xmlid)` from `sor_technical_menu`. This keeps all native menu modification logic in one owner.

**ReceiptSelector widget fix:** The native `account.move` form uses `widget="receipt_selector"` on `move_type`. `ReceiptSelector` calls `useService('lazy_session')` — a service owned by `point_of_sale`. Without POS installed, every `account.move` form render crashes with a JS service error. The fix replaces the widget with `radio` via XPath inheritance. `ReceiptSelector` extends `RadioField`, so the UX is identical.

---

## 4. Models

No new models. No model extensions.

---

## 5. Views

| File | Description |
|------|------------|
| `views/account_move_views.xml` | Inherits `account.view_move_form`; replaces `receipt_selector` widget with `radio` on `move_type` field |

---

## 6. Module file structure

```
sor_accounting/
├── __manifest__.py        # module metadata, hook declarations
├── __init__.py            # imports models (empty) and hook functions
├── hooks.py               # post_init_hook (suppress), uninstall_hook (restore)
├── models/
│   └── __init__.py        # empty
├── views/
│   └── account_move_views.xml  # ReceiptSelector widget fix
├── security/
│   └── ir.model.access.csv     # empty (no new models)
├── i18n/
│   └── sor_accounting.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_accounting.py
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## 7. Critical files

| File | Purpose |
|------|---------|
| `hooks.py` | All menu suppression logic; `SUPPRESSED_MENUS` list is the authoritative registry of what is hidden |
| `views/account_move_views.xml` | ReceiptSelector crash fix — do not remove without verifying POS is installed |

---

## 8. Composability boundary

| Installation | Behaviour |
|-------------|-----------|
| `sor_accounting` alone | GL menus suppressed; ReceiptSelector fix active; no invoice features |
| `sor_accounting` + `sor_buyer_invoice` | Event-invoice link layer active on top of suppressed GL surface |
| Without `sor_accounting` | `account` module not guaranteed present; GL surface unsuppressed; ReceiptSelector crash possible |

---

## 9. Special concerns

**Menu suppression is idempotent:** `set_menu_developer_only` adds `base.group_no_one` to `groups_id` only if not already present. Safe to call multiple times.

**`uninstall_hook` scope:** `set_menu_unrestricted` removes `base.group_no_one` from the menu's `groups_id`. If an administrator has manually added other group restrictions to the same menu items, those are preserved — only the `group_no_one` restriction is removed.

---

## 10. Running the tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_accounting
```

---

## 11. Story reference

Story 01 — `sor_accounting`: `.backlog/current/Auction House Invoice/stories/01_SOR-Accounting-Foundation.md`
