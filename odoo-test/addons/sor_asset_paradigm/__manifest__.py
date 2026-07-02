{
    'name': 'SOR Asset Paradigm',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['product', 'stock', 'mail', 'sor_technical_menu'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'views/sor_asset_paradigm_rule_views.xml',
        'views/product_template_views.xml',
    ],
    'application': False,
    'auto_install': False,
    'installable': True,
}
