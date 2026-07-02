# -*- coding: utf-8 -*-
{
    'name': 'SOR Navbar',
    'version': '19.0.1.0.0',
    'category': 'Customization',
    'summary': 'NavBar component overrides (XML/HTML/JS) for Pattern Lab Digital Twin',
    'description': """
SOR Navbar
==========
This module provides NavBar component overrides (templates, structure) for Odoo 19,
designed using Pattern Lab and synced bidirectionally. Theme (CSS/SCSS) lives in sor_theme.
    """,
    'depends': ['web'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            # Replace web's navbar template so only one web.NavBar is registered (avoids "Template already exists").
            ('remove', 'web/static/src/webclient/navbar/navbar.xml'),
            'sor_navbar/static/src/webclient/navbar/navbar.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
