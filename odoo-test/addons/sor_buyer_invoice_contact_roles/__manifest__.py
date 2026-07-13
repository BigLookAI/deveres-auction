{
    'name': 'SOR Buyer Invoice – Contact Roles Bridge',
    'depends': ['sor_buyer_invoice', 'sor_contact_roles'],
    'auto_install': True,
    'application': False,
    'category': 'Hidden/Technical',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'security/sor_buyer_invoice_contact_roles_rules.xml',
    ],
}
