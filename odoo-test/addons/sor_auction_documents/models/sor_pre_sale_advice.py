import base64

from odoo import api, fields, models


class SorPreSaleAdvice(models.Model):
    _name = 'sor.pre.sale.advice'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Pre-Sale Advice'
    _order = 'event_id, consignor_id'
    _check_company_auto = True

    name = fields.Char(
        string='Reference',
        compute='_compute_name',
        store=True,
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
        inverse_name='pre_sale_advice_id',
        string='Lots',
    )

    @api.depends('event_id.sale_number', 'consignor_id.ref')
    def _compute_name(self):
        for rec in self:
            ref = rec.consignor_id.ref or str(rec.consignor_id.id)
            sale = rec.event_id.sale_number or ''
            rec.name = f'PSA/{sale}/{ref}' if sale else f'PSA/{ref}'

    def action_send_by_email(self):
        self.ensure_one()
        report = self.env.ref('sor_auction_documents.action_report_sor_pre_sale_advice')
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
                'default_subject': f'Pre-Sale Advice — {self.event_id.name}',
            },
        }
