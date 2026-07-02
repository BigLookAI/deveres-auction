{
    'name': 'SOR Consignment Agreements',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Technical',
    'summary': '',
    'depends': ['sor_legal_agreement', 'sor_tracking'],
    'auto_install': True,
    'application': False,
    'data': [
        'security/ir.model.access.csv',
        'views/sor_agreement_views.xml',
        'report/consignment_agreement_report.xml',
    ],
    'license': 'LGPL-3',
}
