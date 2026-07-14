import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    lots = env['sor.lot'].search([])
    if lots:
        # sellers_commission_pct changed from plain stored Float to store=True computed+inverse.
        # Odoo does not automatically recompute existing records when the field definition changes
        # during upgrade. Invalidate the field on all existing lots so the next flush re-evaluates
        # the 3-level cascade (lot-level override → consignor override → company default).
        lots.invalidate_recordset(['sellers_commission_pct'])
        env.flush_all()
        _logger.info(
            "sor_commercial_auction_house: recomputed sellers_commission_pct on %s lots",
            len(lots),
        )
