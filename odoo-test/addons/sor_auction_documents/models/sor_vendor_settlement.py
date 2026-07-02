import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SorVendorSettlement(models.Model):
    _name = 'sor.vendor.settlement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Vendor Settlement Statement'
    _order = 'name desc'
    _check_company_auto = True

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('payment_confirmed', 'Payment Confirmed'),
            ('sent', 'Sent'),
            ('cancelled', 'Cancelled'),
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
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
    )
    event_id = fields.Many2one(
        comodel_name='sor.event',
        string='Auction Event',
        required=True,
        check_company=True,
        ondelete='restrict',
    )
    consignor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Consignor',
        required=True,
        check_company=True,
    )
    lot_ids = fields.One2many(
        comodel_name='sor.lot',
        inverse_name='vendor_settlement_id',
        string='Lots',
    )
    total_hammer = fields.Monetary(
        string='Total Hammer',
        compute='_compute_totals',
        store=True,
    )
    total_commission = fields.Monetary(
        string='Total Commission',
        compute='_compute_totals',
        store=True,
    )
    net_proceeds = fields.Monetary(
        string='Net Proceeds',
        compute='_compute_totals',
        store=True,
    )

    @api.depends('lot_ids.hammer_price', 'lot_ids.sellers_commission_pct')
    def _compute_totals(self):
        for vss in self:
            hammer = sum(vss.lot_ids.mapped('hammer_price'))
            commission = sum(
                lot.hammer_price * lot.sellers_commission_pct / 100.0
                for lot in vss.lot_ids
            )
            vss.total_hammer = hammer
            vss.total_commission = commission
            vss.net_proceeds = hammer - commission

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company = self.env['res.company'].browse(
                    vals.get('company_id', self.env.company.id),
                )
                seq_number = (
                    self.env['ir.sequence']
                    .with_company(company)
                    .next_by_code('sor.vendor.settlement')
                    or 'New'
                )
                event_id = vals.get('event_id')
                if event_id:
                    event = self.env['sor.event'].browse(event_id)
                    sale_number = event.sale_number if event.sale_number else ''
                else:
                    sale_number = ''
                vals['name'] = f"{seq_number}/{sale_number}" if sale_number else seq_number
        return super().create(vals_list)

    def action_confirm_payment(self):
        for vss in self:
            if vss.state != 'draft':
                raise UserError(_('Only Draft statements can be confirmed.'))
        self.write({'state': 'payment_confirmed'})

    def action_cancel(self):
        for vss in self:
            if vss.state != 'draft':
                raise UserError(_('Only Draft statements can be cancelled.'))
        self.write({'state': 'cancelled'})

    def action_send_by_email(self):
        self.ensure_one()
        if self.state == 'payment_confirmed':
            self.write({'state': 'sent'})
        report = self.env.ref('sor_auction_documents.action_report_sor_vendor_settlement')
        pdf_content, _content_type = report._render_qweb_pdf(report.id, [self.id])
        attachment = self.env['ir.attachment'].create({
            'name': f'{self.name}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
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
                'default_attachment_ids': [attachment.id],
                'default_subject': f'Vendor Settlement Statement — {self.event_id.name}',
            },
        }

    def action_bulk_mark_sent(self):
        report = self.env.ref('sor_auction_documents.action_report_sor_vendor_settlement')
        to_send = self.filtered(lambda v: v.state == 'payment_confirmed')
        if not to_send:
            raise UserError(_('No Payment Confirmed statements selected.'))
        for vss in to_send:
            if not vss.consignor_id.email:
                continue
            pdf_content, _content_type = report._render_qweb_pdf(report.id, [vss.id])
            attachment = self.env['ir.attachment'].create({
                'name': f'{vss.name}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': vss._name,
                'res_id': vss.id,
                'mimetype': 'application/pdf',
            })
            vss.message_post(
                email_from=vss.company_id.email,
                partner_ids=[vss.consignor_id.id],
                subject=_('Vendor Settlement Statement — %s') % vss.event_id.name,
                body=_('Please find your Vendor Settlement Statement for %s attached.') % vss.event_id.name,
                attachment_ids=[attachment.id],
            )
            vss.write({'state': 'sent'})
