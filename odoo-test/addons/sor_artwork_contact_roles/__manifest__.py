# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SOR Artwork – Contact Roles Bridge',
    'depends': ['sor_artwork', 'sor_contact_roles'],
    'auto_install': True,
    'application': False,
    'category': 'Hidden/Technical',
    'version': '1.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/sor_artwork_contact_roles_views.xml',
    ],
}
