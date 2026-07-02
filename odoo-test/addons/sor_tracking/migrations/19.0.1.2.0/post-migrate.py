from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    ResCompany = env['res.company']
    for company in ResCompany.search([]):
        ResCompany.sudo()._sor_tracking_ensure_operation_types(company)
