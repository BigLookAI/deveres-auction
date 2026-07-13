import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # Lots with state='collected' predate the is_collected boolean.
    # Set is_collected=True and restore state to auction_result where known;
    # default to 'sold' for lots with no recorded auction_result (demo data).
    cr.execute("""
        UPDATE sor_lot
        SET is_collected = TRUE,
            state = CASE
                WHEN auction_result IS NOT NULL AND auction_result != '' THEN auction_result
                ELSE 'sold'
            END
        WHERE state = 'collected'
    """)
    updated = cr.rowcount
    _logger.info("BUG-U13 migration: %d collected lot(s) converted to is_collected=True", updated)
