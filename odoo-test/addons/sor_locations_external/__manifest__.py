# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SOR Locations — External Locations',
    'summary': 'Bridge: Contact-linked external locations (sor_locations + sor_contact_roles)',
    'category': 'Hidden/Technical',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'depends': [
        'sor_locations',
        'sor_contact_roles',
    ],
    'post_init_hook': 'post_init_hook',
    'auto_install': True,
    'application': False,
    'installable': True,
    'test': [
        'tests/test_sor_external_locations.py',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/stock_location_external_views.xml',
        'views/menu.xml',
        'views/res_partner_external_views.xml',
    ],
}
