# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SOR Contact Roles',
    'summary': 'Contact role system (Creator, Artist, Contact, Bidder, Consignor, etc.) for galleries, auction houses, and art businesses',
    'category': 'Custom',
    'version': '19.0.1.7.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'depends': [
        'contacts',
        'sor_technical_menu',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/sor_contact_roles_security.xml',
        'data/sor_contact_type_data.xml',
        'views/res_partner_views.xml',
        'views/sor_contact_nav_views.xml',
        'views/sor_contact_type_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'demo': [
        'demo/demo_contacts.xml',
    ],
    'application': False,
    'installable': True,
}
