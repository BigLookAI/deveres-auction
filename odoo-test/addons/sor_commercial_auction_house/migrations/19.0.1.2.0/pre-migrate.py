import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # Add the backing column before Odoo processes the schema (Odoo's ADD COLUMN will be a no-op).
    # Seed from sellers_commission_pct for lots that already have use_custom_vendor_fee = True
    # so the compute method returns the correct custom rate after the upgrade.
    cr.execute("""
        ALTER TABLE sor_lot
        ADD COLUMN IF NOT EXISTS sellers_commission_pct_override double precision DEFAULT 0.0
    """)
    cr.execute("""
        UPDATE sor_lot
        SET sellers_commission_pct_override = sellers_commission_pct
        WHERE use_custom_vendor_fee = TRUE
    """)
    _logger.info(
        "sor_commercial_auction_house: seeded sellers_commission_pct_override "
        "from sellers_commission_pct for %s custom-override lots",
        cr.rowcount,
    )
