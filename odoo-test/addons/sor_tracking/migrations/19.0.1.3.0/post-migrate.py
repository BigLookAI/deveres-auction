from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env['res.company'].search([]):
        env['res.company'].sudo()._sor_tracking_ensure_external_location(company)
