from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    sor_lot_id = fields.Many2one(
        comodel_name='sor.lot',
        string='Lot',
        ondelete='set null',
    )
    sor_line_type = fields.Selection(
        selection=[
            ('hammer', 'Hammer'),
            ('buyers_premium', "Buyer's Premium"),
        ],
        string='SOR Line Type',
    )
    sor_buyers_premium_pct = fields.Float(
        string="Buyer's Premium %",
        digits=(10, 1),
    )
