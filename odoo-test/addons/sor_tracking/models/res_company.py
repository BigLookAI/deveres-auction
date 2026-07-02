from odoo import api, models

from odoo.addons.sor_tracking.hooks import _ensure_pool_locations


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            _ensure_pool_locations(self.env, company)
        return companies
