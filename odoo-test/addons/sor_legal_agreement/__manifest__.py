{
    'name': 'SOR Legal Agreements',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'category': 'Hidden/Technical',
    'depends': ['product', 'stock', 'sor_technical_menu'],
    'data': [
        'data/sor_agreement_sequence.xml',
        'data/ir_cron_data.xml',
        'security/ir.model.access.csv',
        'security/sor_agreement_rules.xml',
        'report/sor_agreement_report.xml',
        'report/sor_agreement_template.xml',
        'views/sor_agreement_views.xml',
        'views/sor_agreement_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'demo': [
        'demo/demo_agreements.xml',
    ],
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
