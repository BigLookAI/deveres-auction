{
    'name': 'SOR Consignment Agreements × Auction House',
    'version': '19.0.1.0.0',
    'summary': 'Adds auction house commercial terms to consignment agreements',
    'category': 'Hidden/Technical',
    'depends': ['sor_consignment_agreements', 'sor_commercial_auction_house'],
    'data': [
        'security/ir.model.access.csv',
        'views/sor_agreement_views.xml',
        'report/sor_agreement_report_bridge.xml',
    ],
    'demo': [
        'demo/demo_agreements.xml',
    ],
    'auto_install': True,
    'application': False,
    'license': 'LGPL-3',
}
