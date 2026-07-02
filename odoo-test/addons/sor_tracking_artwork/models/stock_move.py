from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    sor_draft_lot_name = fields.Char(
        string='Serial Number',
        help=(
            'Serial pre-assigned in Draft. Avoids creating a move line in Draft, '
            'which would trigger Odoo stock reservation and auto-advance the picking '
            'to Ready state. Converted to a stock.lot at Mark as Todo (action_confirm).'
        ),
    )
