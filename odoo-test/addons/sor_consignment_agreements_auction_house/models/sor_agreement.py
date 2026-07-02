from odoo import api, fields, models


class SorAgreement(models.Model):
    _inherit = 'sor.agreement'

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        store=False,
    )
    catalogue_estimate = fields.Monetary(
        string='Catalogue Estimate',
        currency_field='currency_id',
    )
    reserve_price = fields.Monetary(
        string='Reserve Price',
        currency_field='currency_id',
    )
    vendor_commission_pct = fields.Float(
        string='Vendor Commission (%)',
        digits=(5, 2),
    )
    vendor_commission_amount = fields.Monetary(
        string='Vendor Commission',
        currency_field='currency_id',
        compute='_compute_vendor_commission_amount',
        store=False,
    )

    @api.depends('vendor_commission_pct')
    def _compute_vendor_commission_amount(self):
        # MVP: returns 0.0 — full computation requires lot-linking (D2 scope)
        for agreement in self:
            agreement.vendor_commission_amount = 0.0
