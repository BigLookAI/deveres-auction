{
    'name': 'SOR Accounting',
    'version': '19.0.1.0.0',
    'summary': 'Accounting infrastructure foundation — installs account module and restricts GL surfaces to developer mode',
    'category': 'Hidden/Technical',
    'depends': ['account', 'base_setup', 'sor_technical_menu'],
    'data': [
        'views/account_move_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
