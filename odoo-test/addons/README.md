# deVeres sandbox addons — provenance

Snapshot of the SOR module stack used by `../restore.sh` to boot the restored
April-auction test database (Odoo 19).

| What | Where from |
|---|---|
| `sor_*` module sources | synced 2-Jul-2026 from `BigLookAI/BL-Odoo-System-of-Record` @ `11b6c4497` (DGX checkout `~/Gemma4/BL-Odoo-System-of-Record/addons`) |
| `sor_lotting_contact_roles/`, `sor_buyer_invoice_contact_roles/` | **reconstructed locally** — installed in the April-test DB but absent from the repo's main branch; fields/views recovered verbatim from the dump (see each `__manifest__.py`) |
| `*_compat.py` files inside `sor_lotting`, `sor_contact_roles`, `sor_commercial_auction_house`, `sor_auction_documents`, `sor_buyer_invoice_auction_house` | **reconstructed locally** — the DB was created by newer module versions (e.g. sor_contact_roles 1.7.0 vs available 1.5.0); each file's header lists the exact version drift it covers |

When the SOR team's current tree becomes available, re-sync the modules and
delete the `*_compat.py` files plus the two reconstructed bridge modules:

```bash
rsync -az -e "ssh -i ~/.ssh/artfest_deploy" --include='sor_*/***' --exclude='*' \
  syadav@100.101.39.73:Gemma4/BL-Odoo-System-of-Record/addons/ ./
```
