# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SOR Locations — Artist Studios',
    'summary': 'Bridge: Artist Studios as off-premises internal locations (sor_locations + sor_contact_roles)',
    'category': 'Hidden/Technical',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'depends': [
        'sor_locations',
        'sor_artwork_contact_roles',
    ],
    'post_init_hook': 'post_init_hook',
    'auto_install': True,
    'application': False,
    'installable': True,
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/stock_location_studio_views.xml',
        'views/menu.xml',
        'views/res_partner_studio_views.xml',
    ],
}
