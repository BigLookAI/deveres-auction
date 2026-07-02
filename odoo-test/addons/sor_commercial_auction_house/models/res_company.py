from odoo import api, fields, models

from .. import hooks


class ResCompany(models.Model):
    _inherit = 'res.company'

    hammer_price_vat_included = fields.Boolean(
        string='Hammer Price VAT Included',
        default=False,
        help='Company-wide default for new lots. Individual lots can override this setting.',
    )
    auction_vat_notice = fields.Text(
        string='Auction VAT Notice',
        help=(
            'Statutory notice text printed on buyer invoices when Hammer Price VAT Included '
            'is enabled. Leave empty to suppress the notice block. Set wording appropriate '
            "to the company's jurisdiction."
        ),
    )
    fee_default_ids = fields.One2many(
        comodel_name='sor.fee.default',
        inverse_name='company_id',
        string='Vendor Fee Schedule',
    )
    buyers_premium_tier_ids = fields.One2many(
        comodel_name='sor.buyers.premium.tier',
        inverse_name='company_id',
        string="Buyer's Premium Tiers",
    )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            hooks._ensure_fee_defaults(self.env, company)
            hooks._ensure_buyers_premium_tier(self.env, company)
        return companies
