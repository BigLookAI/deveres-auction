from odoo import api, models

from ..hooks import _ensure_auction_journal, _ensure_buyer_invoice_sequence


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            _ensure_auction_journal(self.env, company)
            _ensure_buyer_invoice_sequence(self.env, company)
        return companies
