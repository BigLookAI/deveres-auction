{
    'name': 'SOR Buyer Invoice',
    'version': '19.0.1.1.0',
    'summary': 'Business-model-agnostic event-invoice link layer: links invoices to events via smart button',
    'category': 'Hidden/Technical',
    'depends': ['sor_accounting', 'sor_events'],
    'data': [
        'security/ir.model.access.csv',
        'views/sor_event_views.xml',
        'views/account_move_views.xml',
        'report/account_invoice_report.xml',
        'report/report_web_layout_header_suppression.xml',
    ],
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
