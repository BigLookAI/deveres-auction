{
    'name': 'SOR Commercial Auction House',
    'version': '19.0.1.4.0',
    'description': (
        'Bridge: links sor_business_model and sor_events_auction — adds per-event '
        'commercial flag, fee schedule (vendor fees and tiered buyer\'s premium), '
        'and fee-aware break-even value computation.'
    ),
    'author': 'BigLookAI',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['sor_business_model', 'sor_events_auction'],
    'application': False,
    'auto_install': True,
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/ir.model.access.csv',
        'security/sor_commercial_auction_house_rules.xml',
        'data/sor_commercial_auction_house_suppression_rules.xml',
        'views/res_config_settings_views.xml',
        'views/sor_event_commercial_views.xml',
        'views/sor_lot_commercial_views.xml',
    ],
    'demo': [
        'demo/demo_fees.xml',
    ],
}
