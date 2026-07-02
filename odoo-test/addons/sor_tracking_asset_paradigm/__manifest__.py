{
    'name': 'SOR Tracking — Asset Paradigm Bridge',
    'version': '19.0.1.0.0',
    'author': 'BigLookAI',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['sor_tracking', 'sor_asset_paradigm'],
    'application': False,
    'auto_install': True,
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
    ],
}
