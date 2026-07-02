from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    sor_movement_count = fields.Integer(
        string='Movements',
        compute='_compute_sor_movement_count',
        store=False,
    )

    def _compute_sor_movement_count(self):
        for tmpl in self:
            tmpl.sor_movement_count = self.env['stock.move.line'].search_count([
                ('product_id.product_tmpl_id', '=', tmpl.id),
                ('state', '=', 'done'),
            ])

    def action_view_traceability(self, *args):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Traceability',
            'res_model': 'stock.move.line',
            'view_mode': 'list,form',
            'domain': [
                ('product_id.product_tmpl_id', '=', self.id),
                ('state', '=', 'done'),
            ],
            'context': {'default_product_id': self.product_variant_ids[:1].id},
        }

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if defaults.get('product_type') == 'artwork':
            defaults['tracking'] = 'serial'
        return defaults
