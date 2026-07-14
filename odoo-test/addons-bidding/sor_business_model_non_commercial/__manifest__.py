{
    'name': 'SOR Business Model — Non-Commercial',
    'version': '19.0.1.0.0',
    'depends': ['sor_business_model'],
    'application': False,
    'auto_install': True,
    'category': 'Hidden/Technical',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'data/sor_business_model_rules.xml',
        'data/sor_business_model_rule_manifestations.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/res_company_views.xml',
    ],
    'demo': [
        'demo/demo_company.xml',
    ],
}
