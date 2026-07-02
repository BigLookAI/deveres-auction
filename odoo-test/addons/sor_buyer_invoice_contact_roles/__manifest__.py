# Reconstructed locally by Cimelium (2-Jul-2026). The April-test database has
# this module installed but it owns NO ir.model.data records (no fields, views,
# security or data) — it is a pure Python bridge in the SOR dev tree whose
# source is not in BigLookAI/BL-Odoo-System-of-Record@main. This empty shell
# keeps the module registry consistent so the restored database boots without
# "module not found" degradation. Any Python-only behaviour of the original
# (e.g. role flags on invoice partners) is NOT reproduced here.
{
    'name': 'SOR Buyer Invoice – Contact Roles Bridge',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Bridge: sor_buyer_invoice + sor_contact_roles (reconstructed shell)',
    'author': 'BigLook',
    'license': 'LGPL-3',
    'depends': ['sor_buyer_invoice', 'sor_contact_roles'],
    'data': [],
    'auto_install': True,
    'installable': True,
}
