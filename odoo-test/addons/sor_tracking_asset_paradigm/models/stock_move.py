from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    sor_all_unique_objects = fields.Boolean(
        compute='_compute_sor_all_unique_objects_move',
        store=False,
    )

    @api.depends('picking_id.sor_all_unique_objects')
    def _compute_sor_all_unique_objects_move(self):
        for move in self:
            move.sor_all_unique_objects = (
                move.picking_id.sor_all_unique_objects if move.picking_id else False
            )

    @api.onchange('product_id')
    def _onchange_product_id_sor_tracking_asset_paradigm(self):
        if not self.product_id:
            return
        if self.product_id.asset_paradigm == 'unique_object':
            self.product_uom_qty = 1

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            product_id = vals.get('product_id')
            if product_id and not vals.get('product_uom_qty'):
                product = self.env['product.product'].browse(product_id)
                if product.asset_paradigm == 'unique_object':
                    vals['product_uom_qty'] = 1
        return super().create(vals_list)

    def _action_confirm(self, *args, **kwargs):
        for move in self:
            if (move.product_id.asset_paradigm == 'unique_object'
                    and not move.product_uom_qty):
                move.product_uom_qty = 1
        return super()._action_confirm(*args, **kwargs)
