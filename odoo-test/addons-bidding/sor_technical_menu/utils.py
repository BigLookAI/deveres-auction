def set_menu_active(env, xmlid, active):
    """Suppress or restore a native Odoo menu item by xmlid."""
    menu = env.ref(xmlid, raise_if_not_found=False)
    if menu:
        menu.sudo().write({'active': active})


def set_menu_developer_only(env, xmlid):
    """Restrict a menu to developer mode only (groups=base.group_no_one, active=True).

    Prefer this over set_menu_active(False) when the intent is developer visibility:
    the full menu tree (parent + all children) becomes accessible in developer mode.
    """
    menu = env.ref(xmlid, raise_if_not_found=False)
    if menu:
        group = env.ref('base.group_no_one', raise_if_not_found=False)
        if group:
            menu.sudo().write({'active': True, 'group_ids': [(6, 0, [group.id])]})


def set_menu_unrestricted(env, xmlid):
    """Restore a menu to normal visibility (clear groups restriction, active=True)."""
    menu = env.ref(xmlid, raise_if_not_found=False)
    if menu:
        menu.sudo().write({'active': True, 'group_ids': [(5, 0, 0)]})
