from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    default_sellers_commission_pct = fields.Float(
        string="Default Seller's Commission %",
        help=(
            "Default seller's commission rate for lots consigned by this vendor. "
            "When non-zero, takes precedence over the company's Vendor Fee Schedule rate. "
            "Zero means use the company default."
        ),
    )
