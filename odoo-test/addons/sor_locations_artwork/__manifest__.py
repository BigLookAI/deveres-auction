# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SOR Locations — Artwork',
    'summary': 'Bridge: Artwork location assignment and dashboard (sor_locations + sor_artwork)',
    'category': 'Hidden/Technical',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'depends': [
        'sor_locations',
        'sor_artwork',
    ],
    'auto_install': True,
    'application': False,
    'installable': True,
    'demo': [
        'demo/demo_artwork_locations.xml',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/stock_location_views.xml',
        'views/stock_warehouse_views.xml',
        'views/menu.xml',
    ],
}
