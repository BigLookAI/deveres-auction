{
    'name': 'SOR Modern Theme',
    'version': '19.0.1.0.0',
    'category': 'Customization',
    'summary': 'Modern theme for Odoo 19 with Pattern Lab Digital Twin',
    'description': """
SOR Modern Theme
================
This module provides a modern theme for Odoo 19, designed using Pattern Lab
and synced bidirectionally with Odoo components.

Features:
----------
* Modern UI components designed in Pattern Lab
* Bidirectional sync between Pattern Lab and Odoo
* Asset replacement system for seamless integration
* Digital Twin architecture for design-development workflow
    """,
    'depends': ['web'],
    'data': [
        'data/ir_asset.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # 'sor_theme/static/src/scss/style.scss',
            'sor_theme/static/src/scss/_pattern_lab_navbar_preview.scss',  # add this - single source, upgrade picks up changes
            'sor_theme/static/src/scss/form_controller_overrides.scss',
        ],
        'web._assets_primary_variables': [
            'sor_theme/static/src/scss/tokens/pl/colors.scss',
            'sor_theme/static/src/scss/tokens/pl/measures.scss',
            'sor_theme/static/src/scss/tokens/pl/gradients.scss',
            'sor_theme/static/src/scss/tokens/odoo/index.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
