{
    'name': 'SOR Lotting',
    'version': '19.0.1.1.0',
    'summary': 'Base lot model for auction cataloguing',
    'description': 'Provides the sor.lot model with catalogue number, product reference, financial estimates, reserve, status lifecycle, and multi-company isolation.',
    'author': 'BigLookAI',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['product', 'mail'],
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'data': [
        'data/sor_lot_sequence.xml',
        'security/ir.model.access.csv',
        'security/sor_lotting_rules.xml',
        'views/sor_lot_views.xml',
    ],
    'demo': [
        'demo/demo_lots.xml',
    ],
}
