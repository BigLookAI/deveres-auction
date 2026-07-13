from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .mail_bulk_send_utils import bulk_send_notification, bulk_send_via_template


class SorPostSaleAdvice(models.Model):
    _name = 'sor.post.sale.advice'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Post-Sale Advice'
    _order = 'event_id, consignor_id'
    _check_company_auto = True

    name = fields.Char(
        string='Reference',
        compute='_compute_name',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('sent', 'Sent'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    event_id = fields.Many2one(
        comodel_name='sor.event',
        string='Auction Event',
        required=True,
        check_company=True,
        ondelete='cascade',
    )
    consignor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Consignor',
        required=True,
        check_company=True,
    )
    lot_ids = fields.One2many(
        comodel_name='sor.lot',
        inverse_name='post_sale_advice_id',
        string='Lots',
    )

    @api.depends('event_id.sale_number', 'consignor_id.ref')
    def _compute_name(self):
        for rec in self:
            ref = rec.consignor_id.ref or str(rec.consignor_id.id)
            sale = rec.event_id.sale_number or ''
            rec.name = f'PSA-POST/{sale}/{ref}' if sale else f'PSA-POST/{ref}'

    def action_send_by_email(self):
        self.ensure_one()
        if self.state == 'draft':
            self.write({'state': 'sent'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': self._name,
                'default_res_ids': [self.id],
                'default_email_from': self.company_id.email,
                'default_partner_ids': [self.consignor_id.id] if self.consignor_id else [],
                'default_template_id': self.env.ref(
                    'sor_auction_documents.mail_template_sor_post_sale_advice',
                ).id,
            },
        }

    def action_bulk_send(self):
        to_send = self.filtered(lambda r: r.state == 'draft' and r.consignor_id)
        if not to_send:
            raise UserError(_('No unsent Post-Sale Advices selected.'))
        not_eligible_count = len(self) - len(to_send)
        template = self.env.ref('sor_auction_documents.mail_template_sor_post_sale_advice')
        sent, skipped = bulk_send_via_template(
            to_send, template,
            _('Post-Sale Advice not sent: %s has no email on file.'),
        )
        sent.write({'state': 'sent'})
        return bulk_send_notification(
            len(sent), len(skipped), _('Post-Sale Advice(s)'), not_eligible_count,
        )
