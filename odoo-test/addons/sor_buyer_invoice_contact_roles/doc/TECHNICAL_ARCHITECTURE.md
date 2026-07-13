# SOR Buyer Invoice × Contact Roles Bridge: Technical Architecture

## 1. Overview

Single-purpose bridge that patches Odoo 19's core partner visibility rule so that
`account.move.partner_ref` (a `related='partner_id.ref'` field) resolves correctly
for art-world contacts. No new models, fields, or Python code — one `ir.rule` override.

**Dependency diagram:**

```
sor_buyer_invoice    sor_contact_roles
         \                /
          \              /
   sor_buyer_invoice_contact_roles   ← patches base.res_partner_rule
```

---

## 2. Module pattern

| Flag | Value | Reason |
|------|-------|--------|
| `auto_install` | `True` | Activates automatically when both parents are installed |
| `application` | `False` | Not a top-level app |
| `category` | `Hidden/Technical` | Bridge — excluded from business category listings |

---

## 3. Architecture decisions

**Why a bridge instead of fixing `sor_contact_roles`?** The rule override is only
needed when buyer invoices are involved. Putting it in `sor_contact_roles` would
apply the relaxed rule to all installations regardless of whether `sor_buyer_invoice`
is installed — a broader change than the minimum required. The broader fix (adding the
override directly to `sor_contact_roles` for all installations) is tracked as a future
`sor_contact_roles` sprint.

**Why `base.res_partner_rule`, not `base.res_partner_rule_private_employee`?**
The rule `base.res_partner_rule_private_employee` does **not exist in Odoo 19** — it
was removed or renamed in the upgrade from Odoo 16/17. The correct Odoo 19 rule is
`base.res_partner_rule`. Using the old ID raises `Cannot update missing record` at
module install time and prevents the bridge from installing.  
*Critical finding: confirmed during Sprint 19 System Testing. See `sor_multi_company.md`.*

**Why `noupdate="1"` on the rule?** Prevents `--update` from resetting any runtime
customisations an administrator may have applied to the domain at runtime.

---

## 4. Models

None — this module adds no new models.

---

## 5. Views

None — this module adds no new views.

---

## 6. Module file structure

```
sor_buyer_invoice_contact_roles/
├── __manifest__.py            — auto_install=True, no version bump needed
├── __init__.py                — empty (no Python modules)
├── security/
│   ├── ir.model.access.csv   — empty (no new models)
│   └── sor_buyer_invoice_contact_roles_rules.xml  — base.res_partner_rule override
├── i18n/
│   └── sor_buyer_invoice_contact_roles.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_buyer_invoice_contact_roles.py
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## 7. Critical files

| File | Purpose |
|------|---------|
| `security/sor_buyer_invoice_contact_roles_rules.xml` | The only functional file — overrides `base.res_partner_rule` (the Odoo 19 partner visibility rule) with a domain that includes `company_id=False` art-world contacts |

---

## 8. Composability boundary

| Installation | `base.res_partner_rule` domain | `partner_ref` on buyer invoice |
|-------------|-------------------------------|-------------------------------|
| `sor_buyer_invoice` only | Odoo 19 default | Standard Odoo behaviour |
| `sor_contact_roles` only | Odoo 19 default | N/A — no buyer invoices |
| Both (this bridge installs) | Relaxed — includes `company_id=False` clause | Resolves correctly for art-world contacts |

---

## 9. Special concerns

**Odoo 19 XML ID correction — `base.res_partner_rule`:**  
Earlier sprint documentation (and the initial module scaffold written for Sprint 19)
referenced `base.res_partner_rule_private_employee` as the rule to override. This rule
does **not exist in Odoo 19**. Every install attempt with the wrong ID produced:

```
Cannot update missing record 'base.res_partner_rule_private_employee' of type 'ir.rule'
```

This left the module in `uninstalled` state. The fix was to replace the XML ID with
`base.res_partner_rule` — the actual Odoo 19 partner visibility rule. This finding has
been propagated to `sor_multi_company.md` (the platform rule about `partner_share` overrides)
so future bridges targeting partner visibility use the correct ID.

**Silent empty-field return:**  
When `base.res_partner_rule` restricts a partner from the user's visible recordset,
ORM `related` field traversal (`related='partner_id.ref'`) silently returns the field's
default value (empty string) instead of raising `AccessError`. There is no error in the
logs. Detection requires noticing that a document field is blank when it should not be,
then tracing the cause via `env['res.partner'].browse(id).ref` in the shell — if the
browse returns an empty recordset, the rule is the cause.

---

## 10. Running the tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_buyer_invoice_contact_roles
```

---

## 11. Story reference

Story 04 — Auction Workflow UX sprint (Sprint 19)
