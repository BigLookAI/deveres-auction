from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    sor_lot_ids = fields.Many2many(
        comodel_name='sor.lot',
        relation='sor_buyer_invoice_lot_rel',
        column1='move_id',
        column2='lot_id',
        string='Lots',
    )

    def action_bulk_send_sor_invoice(self):
        to_send = self.filtered(
            lambda m: m.move_type == 'out_invoice' and m.partner_id,
        )
        if not to_send:
            raise UserError(_('No buyer invoices selected.'))
        # Records excluded here (wrong move_type, e.g. a credit note or vendor bill,
        # or no partner_id) never reach the sent/skipped split below and would
        # otherwise vanish from the notification with no indication they were
        # never considered — see BUG-04.
        not_eligible_count = len(self) - len(to_send)
        sent = to_send.filtered(lambda m: m.partner_id.email)
        skipped = to_send - sent
        for invoice in skipped:
            invoice.message_post(
                body=_('Buyer Invoice not sent: %s has no email on file.')
                % (invoice.partner_id.name or _('Unknown')),
            )
        if sent:
            template = self.env.ref('sor_buyer_invoice_auction_house.mail_template_sor_buyer_invoice_bulk')
            composer = self.env['mail.compose.message'].create({
                'model': 'account.move',
                'res_ids': str(sent.ids),
                'composition_mode': 'mass_mail',
                'template_id': template.id,
                'auto_delete': False,
                'force_send': True,
            })
            composer.action_send_mail()
        if not skipped and not not_eligible_count:
            message = _('%d Buyer Invoice(s) sent.') % len(sent)
            notif_type = 'success'
        else:
            segments = [_('%d Buyer Invoice(s) sent') % len(sent)]
            if skipped:
                segments.append(_('%d skipped — no email on file') % len(skipped))
            if not_eligible_count:
                segments.append(_('%d not eligible (wrong state)') % not_eligible_count)
            message = ', '.join(segments) + '.'
            if skipped:
                message += ' ' + _('See the chatter on each skipped record for details.')
            notif_type = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Send'),
                'message': message,
                'type': notif_type,
                'sticky': bool(skipped or not_eligible_count),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
