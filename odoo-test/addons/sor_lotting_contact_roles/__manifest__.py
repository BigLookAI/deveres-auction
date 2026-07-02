# Reconstructed locally by Cimelium (2-Jul-2026) from the odoo_deveres_april_test
# database backup: the original module source lives in the SOR dev team's tree and
# is not present in BigLookAI/BL-Odoo-System-of-Record@main. Field definitions,
# the partner form view arch and the smart-button action were recovered verbatim
# from ir_model_fields / ir_ui_view in the dump, so this module is drop-in
# compatible with databases where the original 19.0.1.0.0 was installed.
{
    'name': 'SOR Lotting – Contact Roles Bridge',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Consigned lots on the contact form (bridge: sor_lotting + sor_contact_roles)',
    'author': 'BigLook',
    'license': 'LGPL-3',
    'depends': ['sor_lotting', 'sor_contact_roles'],
    'data': ['views/res_partner_views.xml'],
    'auto_install': True,
    'installable': True,
}
