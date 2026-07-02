{
    'name': 'SOR Consignment Auction',
    'version': '19.0.1.0.0',
    'summary': 'Auto-populates lot consignor from consignment intake pickings',
    'depends': ['sor_consignment_agreements', 'sor_auction_documents'],
    'auto_install': True,
    'application': False,
    'category': 'Hidden/Technical',
    'data': [
        'security/ir.model.access.csv',
        'views/sor_lot_consignment_auction_views.xml',
    ],
    'license': 'LGPL-3',
}
