from odoo.addons.sor_technical_menu.utils import (
    set_menu_developer_only,
    set_menu_unrestricted,
)


def post_init_hook(env):
    set_menu_developer_only(env, 'stock.menu_stock_root')


def uninstall_hook(env):
    set_menu_unrestricted(env, 'stock.menu_stock_root')
