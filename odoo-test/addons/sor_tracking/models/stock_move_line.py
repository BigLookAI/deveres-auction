from odoo import api, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.onchange('move_id', 'picking_id')
    def _onchange_sor_tracking_owner(self):
        for line in self:
            if not line.owner_id and line.picking_id and line.picking_id.partner_id:
                line.owner_id = line.picking_id.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('owner_id'):
                continue
            picking_id = vals.get('picking_id')
            if not picking_id:
                continue
            picking = self.env['stock.picking'].browse(picking_id)
            if picking.partner_id:
                vals['owner_id'] = picking.partner_id.id
        return super().create(vals_list)
