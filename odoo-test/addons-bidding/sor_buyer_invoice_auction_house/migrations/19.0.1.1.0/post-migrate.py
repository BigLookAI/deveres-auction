import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.sor_buyer_invoice_auction_house.hooks import (
    _ensure_auction_payment_methods,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # post_init_hook only fires on first install — already-installed companies
    # (every company in scope, since this module is already installed) need
    # this migration to actually receive the new payment method provisioning.
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env['res.company'].search([]):
        _ensure_auction_payment_methods(env, company)
    _logger.info('sor_buyer_invoice_auction_house 19.0.1.1.0 migration: payment methods provisioned')
