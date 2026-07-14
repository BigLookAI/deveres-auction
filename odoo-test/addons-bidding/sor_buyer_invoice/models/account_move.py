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

    def open_payments(self):
        action = super().open_payments()
        if action.get('res_model') == 'account.payment':
            no_create_view = self.env.ref('sor_buyer_invoice.view_account_payment_list_no_create')
            action['views'] = [
                (no_create_view.id, view_type) if view_type == 'list' else (view_id, view_type)
                for view_id, view_type in action['views']
            ]
        return action

    def _get_name_invoice_report(self):
        self.ensure_one()
        if self.sor_event_id:
            return 'sor_buyer_invoice.report_invoice_document_sor_buyer_invoice'
        return super()._get_name_invoice_report()
