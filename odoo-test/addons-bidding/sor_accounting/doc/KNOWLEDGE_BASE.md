# SOR Accounting — Knowledge Base

## 1. Overview

**What it does:** Installs the Odoo `account` module as a dependency and configures the GL surface for auction house use. It restricts general ledger, reporting, and accounting configuration menus to developer mode only, leaving staff with a streamlined Invoicing navigation showing only Customers (Invoices, Credit Notes, Payments, Products, Customers). It also patches the `account.move` form to replace the `ReceiptSelector` widget (which requires Point of Sale) with the standard `radio` widget.

**What it does NOT do:** It does not provision journals, create accounts, or manage accounting entries. That belongs to `sor_buyer_invoice_auction_house` (Auction Sales journal) and Odoo's own chart of accounts infrastructure.

**Dependencies:** `account`, `base_setup`, `sor_technical_menu`

---

## 2. Key fields and models

| Model | Field / Change | Purpose |
|-------|---------------|---------|
| `ir.ui.menu` | `groups_id` set to `base.group_no_one` | Restricts GL menus to developer mode |
| `account.move` | `move_type` widget replaced from `receipt_selector` to `radio` | Avoids POS dependency crash on every invoice form load |

---

## 3. Suppressed menus

The following native Odoo menus are restricted to developer mode (`base.group_no_one`) after install:

| XML ID | Menu path | Reason suppressed |
|--------|----------|------------------|
| `account.menu_board_journal_1` | Invoicing → Dashboard | Not relevant for auction house staff |
| `account.menu_finance_payables` | Invoicing → Vendors | Out of scope for this deployment |
| `account.menu_finance_entries` | Invoicing → Accounting | Raw GL journal entries — developer only |
| `account.account_audit_menu` | Invoicing → Review | Developer only |
| `account.menu_finance_reports` | Invoicing → Reporting | Developer only |
| `account.menu_finance_configuration` | Invoicing → Configuration | Developer only |

Suppression is applied via `post_init_hook` using `sor_technical_menu.set_menu_developer_only`. Restored on uninstall via `uninstall_hook` using `sor_technical_menu.set_menu_unrestricted`.

---

## 4. Configuration

No configuration required after install. Menu suppression is automatic.

To restore a suppressed menu during development: enable developer mode (Settings → Activate Developer Mode), navigate to Settings → Technical → User Interface → Menu Items, find the menu item, and remove `base.group_no_one` from its Allowed Groups.

---

## 5. Developer menu

No SOR developer menu entries in this module.

---

## 6. Building on this module

Modules that add accounting features (journals, invoice sequences, invoice generation) should depend on `sor_accounting` to ensure:
- The `account` module is present
- GL surfaces are already restricted before their own menus are registered
- The ReceiptSelector crash is already patched

Pattern: `'depends': ['sor_accounting', ...]`

---

## 7. Regression checks

**R1 — GL menus hidden from staff:** Log in as a non-developer user. Navigate to Invoicing. Confirm the sidebar shows only: Customers (with Invoices, Credit Notes, Payments, Products, Customers sub-items). Dashboard, Vendors, Accounting, Review, Reporting, Configuration must not appear.

**R2 — GL menus visible in developer mode:** Enable developer mode. Navigate to Invoicing. Confirm all suppressed menus reappear.

**R3 — Invoice form loads without crash:** Navigate to Invoicing → Customers → Invoices. Open any invoice or click New. Confirm the form renders without a JavaScript error in the browser console.

---

## 8. Interoperability

| Module | Interaction |
|--------|------------|
| `sor_buyer_invoice` | Depends on this module; its menus extend the Invoicing nav surface that this module has already configured |
| `sor_buyer_invoice_auction_house` | Depends transitively via `sor_buyer_invoice`; provisions the AUC journal within the `account` infrastructure this module ensures is present |
| `sor_technical_menu` | Provides `set_menu_developer_only` / `set_menu_unrestricted` utilities used by this module's hooks |
