# Post-Sale Document Pipeline — design (13-Jul-2026)

The 8-Jul session defined the after-sale sequence: **post-sale advice 2–3 days
after the sale**, and a **vendor settlement statement a couple of weeks
later**. This documents how that runs on the platform as built.

## What already exists (verified on the demo, 13-Jul)

`sor_auction_documents` is installed (0 dependency errors) and ships the
document set as Odoo QWeb reports:

| Report | When | Source data |
|---|---|---|
| Pre-Sale Advice | before the sale | catalogued lots per consignor |
| **Post-Sale Advice** | 2–3 days after | sold/passed lots per consignor: hammer, fees |
| **Vendor Settlement Statement** | ~2 weeks after | settlement: hammer − seller commission − fees |
| Agreement (sor_legal_agreement) | consignment | consignment terms |

Because the reconciliation pipeline now completes auctions in Odoo
(hammer + buyer + sold — live), **the inputs these documents need are
populated automatically by the import**. The commission percentages
(own-stock furniture 0% / furniture 15% / artwork 10%) live on the lot
(`sellers_commission_pct` + override fields) — being loaded Odoo-side.

## The pipeline

```
Sale completed (imports done)
  ├─ T+2–3 days  → per consignor with sold lots: generate Post-Sale Advice
  │                → review → bulk send (needs the production mail server)
  └─ T+~2 weeks  → per consignor: generate Vendor Settlement Statement
                   → review → send + mark settled
```

## Gaps to close before first production use

1. **Consignor linkage** — settlement documents group by `consignor_id` on
   the lot; the Blue Cubes buyer export doesn't carry consignors, so they
   must come from the seller export / lot setup (already part of the
   Lot List import path).
2. **Production mail server** — the bulk-send formatting bug and SMTP setup
   (Odoo-side, in progress; Mailpit emulates today).
3. **Send tracking** — recommend a lightweight checklist view (per consignor:
   advice sent ✓ / statement sent ✓) — candidate next sprint item.
4. **Timing automation** — an Odoo scheduled action (or a reconciliation-app
   reminder in Activity) at T+2d and T+14d after the auction's date_start.
