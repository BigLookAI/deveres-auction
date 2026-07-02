from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    sor_lot_ids = fields.Many2many(
        comodel_name='sor.lot',
        relation='sor_buyer_invoice_lot_rel',
        column1='move_id',
        column2='lot_id',
        string='Lots',
    )
