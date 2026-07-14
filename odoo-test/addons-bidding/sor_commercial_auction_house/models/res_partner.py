from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    default_sellers_commission_pct = fields.Float(
        string="Default Seller's Commission %",
        help=(
            "Stored custom vendor fee rate for this consignor. "
            "Only applied when 'Override Default Commission' is enabled."
        ),
    )
    use_custom_default_commission = fields.Boolean(
        string='Custom Default Commission',
        default=False,
    )
    effective_sellers_commission_pct = fields.Float(
        string="Default Vendor Fee %",
        compute='_compute_effective_sellers_commission_pct',
        inverse='_set_effective_sellers_commission_pct',
        store=False,
        digits=(10, 1),
        help=(
            "Effective vendor fee for lots consigned by this vendor. "
            "When 'Override Default Commission' is enabled, shows this vendor's "
            "custom rate; otherwise reflects the company's default fee schedule."
        ),
    )

    @api.depends('use_custom_default_commission', 'default_sellers_commission_pct')
    def _compute_effective_sellers_commission_pct(self):
        company = self.env.company
        fee = company.fee_default_ids.filtered(
            lambda f: f.fee_type == 'sellers_commission',
        )
        company_rate = fee.rate_pct if fee else 0.0
        for partner in self:
            if partner.use_custom_default_commission:
                partner.effective_sellers_commission_pct = (
                    partner.default_sellers_commission_pct
                )
            else:
                partner.effective_sellers_commission_pct = company_rate

    def _set_effective_sellers_commission_pct(self):
        for partner in self:
            if partner.use_custom_default_commission:
                partner.default_sellers_commission_pct = (
                    partner.effective_sellers_commission_pct
                )
