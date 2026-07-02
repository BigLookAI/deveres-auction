from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    agreement_id = fields.Many2one(
        comodel_name='sor.agreement',
        string='Agreement',
        ondelete='set null',
    )
