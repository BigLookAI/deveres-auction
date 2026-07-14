from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    business_model = fields.Selection(
        related='company_id.business_model',
        readonly=False,
        string='Business Model',
    )
