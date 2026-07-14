from odoo import _, api, fields, models
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
    psa_pending_count = fields.Integer(
        compute='_compute_psa_pending_count',
        store=False,
    )
    posa_pending_count = fields.Integer(
        compute='_compute_posa_pending_count',
        store=False,
    )
    vss_pending_count = fields.Integer(
        compute='_compute_vss_pending_count',
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

    @api.depends('lot_ids', 'lot_ids.state', 'lot_ids.consignor_id', 'lot_ids.pre_sale_advice_id')
    def _compute_psa_pending_count(self):
        for event in self:
            event.psa_pending_count = len(event.lot_ids.filtered(
                lambda lot: lot.state in ('catalogued', 'live')
                and lot.consignor_id
                and not lot.pre_sale_advice_id,
            ))

    @api.depends('lot_ids', 'lot_ids.state', 'lot_ids.consignor_id', 'lot_ids.post_sale_advice_id')
    def _compute_posa_pending_count(self):
        for event in self:
            event.posa_pending_count = len(event.lot_ids.filtered(
                lambda lot: lot.state in ('sold', 'passed')
                and lot.consignor_id
                and not lot.post_sale_advice_id,
            ))

    @api.depends('lot_ids', 'lot_ids.state', 'lot_ids.consignor_id', 'lot_ids.vendor_settlement_id')
    def _compute_vss_pending_count(self):
        for event in self:
            event.vss_pending_count = len(event.lot_ids.filtered(
                lambda lot: lot.state in ('sold', 'passed')
                and lot.consignor_id
                and not lot.vendor_settlement_id,
            ))

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
        self.message_post(
            body=_('%d Pre-Sale Advice(s) generated.') % len(consignors),
            subtype_xmlid='mail.mt_note',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pre-Sale Advices'),
            'res_model': 'sor.pre.sale.advice',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

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
        self.message_post(
            body=_('%d Post-Sale Advice(s) generated.') % len(consignors),
            subtype_xmlid='mail.mt_note',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Post-Sale Advices'),
            'res_model': 'sor.post.sale.advice',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

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
        self.message_post(
            body=_('%d Vendor Settlement(s) generated.') % len(consignors),
            subtype_xmlid='mail.mt_note',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Settlements'),
            'res_model': 'sor.vendor.settlement',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }
