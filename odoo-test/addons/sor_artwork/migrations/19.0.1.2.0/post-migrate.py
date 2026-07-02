import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.sor_technical_menu.utils import set_menu_developer_only

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    set_menu_developer_only(env, 'stock.menu_stock_root')
    _logger.info(
        'sor_artwork 19.0.1.2.0: stock.menu_stock_root restricted to developer mode only',
    )
