# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SOR Locations',
    'summary': 'Viewing Locations and Rooms for gallery, auction, and collection spaces',
    'category': 'Custom',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'depends': [
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_warehouse_views.xml',
        'views/stock_location_views.xml',
        'views/stock_location_external_views.xml',
        'views/menu.xml',
        'views/menu_overrides.xml',
    ],
    'demo': [
        'demo/demo_locations.xml',
    ],
    'application': False,
    'installable': True,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
}
