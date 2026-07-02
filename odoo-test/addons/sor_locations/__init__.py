# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models


def post_init_hook(env):  # noqa: RUF067
    """Enable Storage Locations on install so Rooms appear without manual user setup."""
    env['res.config.settings'].create({
        'group_stock_multi_locations': True,
    }).execute()


def uninstall_hook(env):  # noqa: RUF067
    """Restore the standard Warehouses and Locations menus when sor_locations
    is removed, reversing the active=False applied by menu_overrides.xml."""
    for xml_id in (
        'stock.menu_action_warehouse_form',
        'stock.menu_action_location_form',
    ):
        menu = env.ref(xml_id, raise_if_not_found=False)
        if menu:
            menu.active = True
