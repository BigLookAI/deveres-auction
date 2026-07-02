from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auction_sale_terms = fields.Html(
        related='company_id.auction_sale_terms',
        readonly=False,
    )
    auction_bank_details = fields.Text(
        related='company_id.auction_bank_details',
        readonly=False,
    )
    hammer_price_vat_included = fields.Boolean(
        related='company_id.hammer_price_vat_included',
        readonly=False,
    )
    auction_vat_notice = fields.Text(
        related='company_id.auction_vat_notice',
        readonly=False,
    )
    auction_licence_ref = fields.Char(
        related='company_id.auction_licence_ref',
        readonly=False,
    )
    auction_director_signature = fields.Text(
        related='company_id.auction_director_signature',
        readonly=False,
    )
