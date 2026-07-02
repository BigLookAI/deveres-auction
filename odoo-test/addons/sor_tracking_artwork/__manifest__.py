{
    'name': 'SOR Tracking — Artwork Bridge',
    'version': '19.0.1.0.0',
    'author': 'BigLookAI',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['sor_tracking', 'sor_artwork'],
    'application': False,
    'auto_install': True,
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/ir.model.access.csv',
        'data/sor_tracking_artwork_sequence.xml',
        'views/stock_lot_views.xml',
        'views/stock_move_views.xml',
    ],
}
