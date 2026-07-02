# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SOR Artwork Management',
    'summary': 'Artwork management system with artwork-specific attributes for paintings, sculptures, prints, and other art types',
    'category': 'Custom',
    'version': '19.0.1.2.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'depends': [
        'product',
        'sor_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sor_art_product_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'demo': [
        'demo/demo_artworks.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sor_artwork/static/src/scss/artwork_images.scss',
        ],
    },
    'application': False,
    'installable': True,
}
