{
    'name': 'SOR Business Model',
    'version': '19.0.1.0.0',
    'depends': ['product', 'base', 'sor_technical_menu'],
    'application': False,
    'auto_install': False,
    'category': 'Hidden/Technical',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/sor_business_model_rule_views.xml',
        'views/res_config_settings_views.xml',
    ],
}
