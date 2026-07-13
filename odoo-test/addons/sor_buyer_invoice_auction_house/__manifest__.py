{
    'name': 'SOR Buyer Invoice × Auction House',
    'version': '19.0.1.1.0',
    'summary': "Auction-specific buyer invoice bridge: AUC journal, lot fields, generation, buyer's premium and VAT scheme",
    'category': 'Hidden/Technical',
    'depends': ['sor_buyer_invoice', 'sor_commercial_auction_house'],
    'data': [
        'data/sor_buyer_invoice_auction_house_sequence.xml',
        'data/server_actions.xml',
        'security/ir.model.access.csv',
        'views/sor_event_views.xml',
        'views/account_move_views.xml',
        'report/account_invoice_report_bridge.xml',
        'data/mail_template_data.xml',
    ],
    'demo': [
        'demo/demo_lots_auction.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'auto_install': True,
    'application': False,
    'license': 'LGPL-3',
}
