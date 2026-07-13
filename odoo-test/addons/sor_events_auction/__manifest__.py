{
    'name': 'SOR Events Auction',
    'version': '19.0.1.1.0',
    'description': (
        'Bridge: links sor_events and sor_lotting — adds auction-specific '
        'fields to events and links lots to auctions.'
    ),
    'author': 'BigLookAI',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['sor_events', 'sor_lotting'],
    'application': False,
    'auto_install': True,
    'data': [
        'views/sor_events_auction_views.xml',
    ],
    'demo': [
        'demo/demo_auction_links.xml',
    ],
}
