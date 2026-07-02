from odoo import models

from odoo.addons.sor_buyer_invoice_auction_house.hooks import _ensure_auction_journal


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _post_load_data(self, template_code, company, template_data):
        super()._post_load_data(template_code, company, template_data)
        _ensure_auction_journal(self.env, company)
