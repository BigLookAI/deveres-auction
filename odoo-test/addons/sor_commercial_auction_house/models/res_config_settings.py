from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fee_default_ids = fields.One2many(
        related='company_id.fee_default_ids',
        readonly=False,
    )
    buyers_premium_tier_ids = fields.One2many(
        related='company_id.buyers_premium_tier_ids',
        readonly=False,
    )
