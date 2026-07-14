{
    'name': 'SOR Events',
    'version': '19.0.1.0.0',
    'summary': 'Base event model for gallery and auction events',
    'description': 'Provides the sor.event model with type, schedule, status lifecycle, and multi-company isolation.',
    'author': 'BigLookAI',
    'license': 'LGPL-3',
    'category': 'Hidden/Technical',
    'depends': ['base', 'mail', 'sor_technical_menu'],
    'application': False,
    'auto_install': False,
    'data': [
        'security/ir.model.access.csv',
        'security/sor_events_rules.xml',
        'views/sor_event_views.xml',
    ],
    'demo': [
        'demo/demo_events.xml',
    ],
}
