from odoo import api, fields, models

from .. import hooks


class ResCompany(models.Model):
    _inherit = 'res.company'

    vat_margin_scheme = fields.Boolean(
        string='VAT Margin Scheme',
        default=False,
        help='Company-wide default for new lots. Individual lots can override this setting.',
    )
    auction_vat_notice = fields.Html(
        string='Auction VAT Notice',
        help=(
            'Statutory notice text printed on buyer invoices when VAT Margin Scheme '
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
