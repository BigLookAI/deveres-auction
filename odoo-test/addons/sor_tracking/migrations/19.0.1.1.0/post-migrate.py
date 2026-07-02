import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    _logger.info('sor_tracking: backfilling sor_movement_state for existing pickings')
    cr.execute("""
        UPDATE stock_picking
        SET sor_movement_state =
            CASE
                WHEN state = 'done'   THEN 'confirmed'
                WHEN state = 'cancel' THEN 'cancelled'
                ELSE 'queued'
            END
        WHERE sor_movement_state IS NULL
    """)
    _logger.info(
        'sor_tracking: backfilled sor_movement_state for %d pickings',
        cr.rowcount,
    )
