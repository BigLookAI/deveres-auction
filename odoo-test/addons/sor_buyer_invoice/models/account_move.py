from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    sor_event_id = fields.Many2one(
        comodel_name='sor.event',
        string='Event',
        ondelete='set null',
        index=True,
    )

    partner_ref = fields.Char(
        related='partner_id.ref',
        string='Customer Code',
        store=False,
    )
