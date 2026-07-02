{
    'name': 'SOR Asset Paradigm — Baseline',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['sor_asset_paradigm'],
    'data': [
        'security/ir.model.access.csv',
        'data/baseline_product_data.xml',
        'views/baseline_product_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'application': False,
    'auto_install': True,
    'installable': True,
}
