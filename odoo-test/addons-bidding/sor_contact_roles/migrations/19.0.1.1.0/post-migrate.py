import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-migrate: drop is_buyer and is_consignor columns from res_partner."""
    if not version:
        return

    cr.execute("ALTER TABLE res_partner DROP COLUMN IF EXISTS is_buyer")
    _logger.info("Dropped is_buyer column from res_partner.")

    cr.execute("ALTER TABLE res_partner DROP COLUMN IF EXISTS is_consignor")
    _logger.info("Dropped is_consignor column from res_partner.")
