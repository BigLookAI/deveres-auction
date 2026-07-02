import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.sor_technical_menu.utils import set_menu_active

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # Re-suppress stock.menu_stock_root after sor_tracking's 19.0.1.6.0 migration
    # reset it to active=True. post_init_hook only runs on first install, so this
    # migration re-applies the suppression on upgrade for existing installations.
    env = api.Environment(cr, SUPERUSER_ID, {})
    set_menu_active(env, 'stock.menu_stock_root', False)
    _logger.info("sor_artwork migration 19.0.1.1.0: stock.menu_stock_root suppressed")
