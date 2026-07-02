# ── LOCAL 19.0.1.1.0 RECONSTRUCTION (Cimelium, 2-Jul-2026) ────────────────────
# The April-test database was created by sor_lotting 19.0.1.1.0; the source
# available in BigLookAI/BL-Odoo-System-of-Record@main is 19.0.1.0.0. This file
# adds exactly the fields/behaviour 1.1.0 introduced, recovered from
# ir_model_fields and the stored view archs in the dump: chatter on lots, the
# consignor/buyer links, title/description snapshots, the auction result and
# the collection flag. Remove once the real upstream 1.1.0 source is available.
from odoo import _, api, fields, models


class SorLotV110(models.Model):
    _name = 'sor.lot'
    _inherit = ['sor.lot', 'mail.thread', 'mail.activity.mixin']

    lot_title = fields.Char(string='Lot Title')
    lot_description = fields.Html(string='Lot Description')
    lot_item_name = fields.Char(string='Item', compute='_compute_lot_item_name')
    consignor_id = fields.Many2one('res.partner', string='Consignor', index=True)
    buyer_id = fields.Many2one('res.partner', string='Buyer', index=True)
    auction_result = fields.Selection(
        [('sold', 'Sold'), ('passed', 'Passed')], string='Auction Result', copy=False)
    is_collected = fields.Boolean(string='Collected', copy=False)
    collected_display = fields.Char(string='Collected Display',
                                    compute='_compute_collected_display')

    @api.depends('product_id.name')
    def _compute_lot_item_name(self):
        for lot in self:
            lot.lot_item_name = lot.product_id.name or ''

    @api.depends('is_collected')
    def _compute_collected_display(self):
        for lot in self:
            lot.collected_display = _('Collected') if lot.is_collected else _('Not collected')

    def action_mark_collected(self):
        self.write({'is_collected': True})
        return True

    # 1.1.0 relaxed the product link (lots can exist before cataloguing).
    product_id = fields.Many2one(required=False)
