from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    psa_content_top = fields.Html(related='company_id.psa_content_top', readonly=False)
    psa_content_bottom = fields.Html(related='company_id.psa_content_bottom', readonly=False)
    posa_content_top = fields.Html(related='company_id.posa_content_top', readonly=False)
    posa_content_bottom = fields.Html(related='company_id.posa_content_bottom', readonly=False)
    vss_content_top = fields.Html(related='company_id.vss_content_top', readonly=False)
    vss_content_bottom = fields.Html(related='company_id.vss_content_bottom', readonly=False)
    vat_margin_scheme = fields.Boolean(
        related='company_id.vat_margin_scheme',
        readonly=False,
    )
    auction_vat_notice = fields.Html(
        related='company_id.auction_vat_notice',
        readonly=False,
    )
