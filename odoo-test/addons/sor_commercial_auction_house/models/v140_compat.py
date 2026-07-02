# ── LOCAL 19.0.1.4.0 RECONSTRUCTION (Cimelium, 2-Jul-2026) ────────────────────
# The April-test database was created by sor_commercial_auction_house 19.0.1.4.0;
# available source is 19.0.1.0.0. Recovered from ir_model_fields + stored view
# archs: per-lot fee override toggles, the seller-commission override, the
# partner default-commission toggle with its effective-rate display, and the
# company VAT margin scheme flag.
from odoo import api, fields, models


class SorLotV140(models.Model):
    _inherit = 'sor.lot'

    use_custom_vendor_fee = fields.Boolean(string='Custom Vendor Fee')
    use_custom_buyer_premium = fields.Boolean(string='Custom Buyer Premium')
    sellers_commission_pct_override = fields.Float(
        string="Seller's Commission % Override", digits=(10, 1))


class ResPartnerV140(models.Model):
    _inherit = 'res.partner'

    use_custom_default_commission = fields.Boolean(string='Custom Default Commission')
    effective_sellers_commission_pct = fields.Float(
        string="Effective Seller's Commission %",
        compute='_compute_effective_sellers_commission_pct')

    @api.depends('use_custom_default_commission', 'default_sellers_commission_pct')
    def _compute_effective_sellers_commission_pct(self):
        fee = self.env['sor.fee.default'].search([
            ('company_id', '=', self.env.company.id),
            ('fee_type', '=', 'sellers_commission'),
        ], limit=1)
        company_rate = fee.rate_pct if fee else 0.0
        for partner in self:
            partner.effective_sellers_commission_pct = (
                partner.default_sellers_commission_pct
                if partner.use_custom_default_commission and partner.default_sellers_commission_pct
                else company_rate)


class ResCompanyV140(models.Model):
    _inherit = 'res.company'

    vat_margin_scheme = fields.Boolean(string='VAT Margin Scheme')
