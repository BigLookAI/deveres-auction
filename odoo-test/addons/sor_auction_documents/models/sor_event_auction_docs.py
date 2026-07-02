import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class SorEvent(models.Model):
    _inherit = 'sor.event'

    vendor_settlement_count = fields.Integer(
        string='Vendor Settlements',
        compute='_compute_vendor_settlement_count',
        store=False,
    )
    post_sale_advice_count = fields.Integer(
        string='Post-Sale Advices',
        compute='_compute_post_sale_advice_count',
        store=False,
    )
    pre_sale_advice_count = fields.Integer(
        string='Pre-Sale Advices',
        compute='_compute_pre_sale_advice_count',
        store=False,
    )

    def _compute_vendor_settlement_count(self):
        for event in self:
            event.vendor_settlement_count = self.env['sor.vendor.settlement'].search_count([
                ('event_id', '=', event.id),
            ])

    def action_view_vendor_settlements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Settlements'),
            'res_model': 'sor.vendor.settlement',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

    def _compute_post_sale_advice_count(self):
        for event in self:
            event.post_sale_advice_count = self.env['sor.post.sale.advice'].search_count([
                ('event_id', '=', event.id),
            ])

    def _compute_pre_sale_advice_count(self):
        for event in self:
            event.pre_sale_advice_count = self.env['sor.pre.sale.advice'].search_count([
                ('event_id', '=', event.id),
            ])

    def action_view_post_sale_advices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Post-Sale Advices'),
            'res_model': 'sor.post.sale.advice',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

    def action_view_pre_sale_advices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pre-Sale Advices'),
            'res_model': 'sor.pre.sale.advice',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

    def action_generate_pre_sale_advices(self):
        self.ensure_one()
        if self.status in ('closed', 'archived'):
            raise UserError(
                _('Pre-Sale Advice cannot be generated for a closed or archived event.'),
            )
        lots = self.lot_ids.filtered(
            lambda lot: lot.state in ('catalogued', 'live') and lot.consignor_id,
        )
        if not lots:
            raise UserError(
                _('No lots in Catalogued or Live state with a consignor found for this event.'),
            )
        consignors = lots.mapped('consignor_id')
        PreSaleAdvice = self.env['sor.pre.sale.advice']
        for consignor in consignors:
            existing = PreSaleAdvice.search([
                ('event_id', '=', self.id),
                ('consignor_id', '=', consignor.id),
            ], limit=1)
            consignor_lots = lots.filtered(lambda lot: lot.consignor_id == consignor)
            if existing:
                consignor_lots.write({'pre_sale_advice_id': existing.id})
            else:
                advice = PreSaleAdvice.create({
                    'event_id': self.id,
                    'consignor_id': consignor.id,
                    'company_id': self.company_id.id,
                })
                consignor_lots.write({'pre_sale_advice_id': advice.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pre-Sale Advices'),
            'res_model': 'sor.pre.sale.advice',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

    def action_send_all_pre_sale_advices(self):
        self.ensure_one()
        advices = self.env['sor.pre.sale.advice'].search([
            ('event_id', '=', self.id),
        ])
        report = self.env.ref('sor_auction_documents.action_report_sor_pre_sale_advice')
        for advice in advices:
            if not advice.consignor_id.email:
                continue
            pdf_content, _content_type = report._render_qweb_pdf(report.id, [advice.id])
            attachment = self.env['ir.attachment'].create({
                'name': f'{advice.name}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': advice._name,
                'res_id': advice.id,
                'mimetype': 'application/pdf',
            })
            advice.message_post(
                email_from=advice.company_id.email,
                partner_ids=[advice.consignor_id.id],
                subject=_('Pre-Sale Advice — %s') % self.name,
                body=_('Please find your Pre-Sale Advice for %s attached.') % self.name,
                attachment_ids=[attachment.id],
            )

    def action_generate_post_sale_advices(self):
        self.ensure_one()
        if self.status not in ('active', 'closed'):
            raise UserError(
                _('Post-Sale Advice can only be generated for Active or Closed events.'),
            )
        lots = self.lot_ids.filtered(
            lambda lot: lot.state in ('sold', 'passed') and lot.consignor_id,
        )
        if not lots:
            raise UserError(
                _('No lots in Sold or Passed state with a consignor found for this event.'),
            )
        consignors = lots.mapped('consignor_id')
        PostSaleAdvice = self.env['sor.post.sale.advice']
        for consignor in consignors:
            existing = PostSaleAdvice.search([
                ('event_id', '=', self.id),
                ('consignor_id', '=', consignor.id),
            ], limit=1)
            consignor_lots = lots.filtered(lambda lot: lot.consignor_id == consignor)
            if existing:
                consignor_lots.write({'post_sale_advice_id': existing.id})
            else:
                advice = PostSaleAdvice.create({
                    'event_id': self.id,
                    'consignor_id': consignor.id,
                    'company_id': self.company_id.id,
                })
                consignor_lots.write({'post_sale_advice_id': advice.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Post-Sale Advices'),
            'res_model': 'sor.post.sale.advice',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

    def action_send_all_post_sale_advices(self):
        self.ensure_one()
        advices = self.env['sor.post.sale.advice'].search([
            ('event_id', '=', self.id),
        ])
        report = self.env.ref('sor_auction_documents.action_report_sor_post_sale_advice')
        for advice in advices:
            if not advice.consignor_id.email:
                continue
            pdf_content, _content_type = report._render_qweb_pdf(report.id, [advice.id])
            attachment = self.env['ir.attachment'].create({
                'name': f'{advice.name}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': advice._name,
                'res_id': advice.id,
                'mimetype': 'application/pdf',
            })
            advice.message_post(
                email_from=advice.company_id.email,
                partner_ids=[advice.consignor_id.id],
                subject=_('Post-Sale Advice — %s') % self.name,
                body=_('Please find your Post-Sale Advice for %s attached.') % self.name,
                attachment_ids=[attachment.id],
            )

    def action_generate_vendor_settlements(self):
        self.ensure_one()
        if self.status not in ('active', 'closed'):
            raise UserError(
                _('Vendor Settlements can only be generated for Active or Closed events.'),
            )
        lots = self.lot_ids.filtered(
            lambda lot: lot.state in ('sold', 'passed') and lot.consignor_id,
        )
        if not lots:
            raise UserError(
                _('No lots in Sold or Passed state with a consignor found for this event.'),
            )
        consignors = lots.mapped('consignor_id')
        VendorSettlement = self.env['sor.vendor.settlement']
        for consignor in consignors:
            existing = VendorSettlement.search([
                ('event_id', '=', self.id),
                ('consignor_id', '=', consignor.id),
            ], limit=1)
            consignor_lots = lots.filtered(lambda lot: lot.consignor_id == consignor)
            if existing:
                if existing.state == 'draft':
                    consignor_lots.write({'vendor_settlement_id': existing.id})
            else:
                vss = VendorSettlement.create({
                    'event_id': self.id,
                    'consignor_id': consignor.id,
                    'company_id': self.company_id.id,
                })
                consignor_lots.write({'vendor_settlement_id': vss.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Settlements'),
            'res_model': 'sor.vendor.settlement',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }
