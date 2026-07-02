from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sor_all_unique_objects = fields.Boolean(
        string='All Unique Objects',
        compute='_compute_sor_all_unique_objects',
        store=False,
    )

    @api.depends('move_ids.product_id.asset_paradigm')
    def _compute_sor_all_unique_objects(self):
        for picking in self:
            if not picking.move_ids:
                picking.sor_all_unique_objects = False
            else:
                picking.sor_all_unique_objects = all(
                    move.product_id.asset_paradigm == 'unique_object'
                    for move in picking.move_ids
                )
