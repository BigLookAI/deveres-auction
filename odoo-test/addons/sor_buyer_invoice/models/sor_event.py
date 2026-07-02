from odoo import _, api, fields, models


class SorEvent(models.Model):
    _inherit = 'sor.event'

    invoice_count = fields.Integer(
        compute='_compute_invoice_count',
        store=False,
    )

    @api.depends()
    def _compute_invoice_count(self):
        for event in self:
            event.invoice_count = self.env['account.move'].search_count([
                ('sor_event_id', '=', event.id),
            ])

    def action_view_buyer_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Buyer Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('sor_event_id', '=', self.id)],
            'context': {'default_sor_event_id': self.id},
        }
