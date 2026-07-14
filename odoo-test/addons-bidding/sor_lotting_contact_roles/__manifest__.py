{
    'name': 'SOR Lotting — Contact Roles',
    'version': '19.0.1.0.0',
    'author': 'SOR',
    'summary': 'Bridge: consignor lot history on contact forms',
    'depends': ['sor_lotting', 'sor_contact_roles'],
    'auto_install': True,
    'application': False,
    'category': 'Hidden/Technical',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
    ],
    'demo': [
        'demo/demo_lot_partners.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
