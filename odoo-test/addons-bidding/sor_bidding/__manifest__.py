{
    'name': 'SOR Bidding',
    'version': '19.0.1.0.0',
    'description': 'Bridge: links sor_lotting and sor_contact_roles — adds bid recording to lots with bidder contact type.',
    'author': 'BigLookAI',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['sor_lotting', 'sor_contact_roles'],
    'application': False,
    'auto_install': True,
    'data': [
        'security/ir.model.access.csv',
        'security/sor_bidding_rules.xml',
        'data/sor_bidding_data.xml',
        'views/sor_bidding_views.xml',
    ],
    'demo': [
        'demo/demo_bids.xml',
    ],
}
