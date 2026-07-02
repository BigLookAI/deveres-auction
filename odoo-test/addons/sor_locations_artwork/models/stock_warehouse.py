# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    artwork_count = fields.Integer(
        string='Artworks',
        compute='_compute_artwork_count',
    )

    def _compute_artwork_count(self):
        for warehouse in self:
            if not warehouse.view_location_id:
                warehouse.artwork_count = 0
                continue
            child_locations = self.env['stock.location'].search([
                ('id', 'child_of', warehouse.view_location_id.id),
                ('usage', 'in', ['internal', 'customer']),
            ])
            warehouse.artwork_count = self.env['product.template'].search_count([
                ('current_location_id', 'in', child_locations.ids),
                '|', ('company_id', '=', False),
                     ('company_id', '=', warehouse.company_id.id),
            ])

    def action_open_artworks(self):
        self.ensure_one()
        child_locations = self.env['stock.location'].search([
            ('id', 'child_of', self.view_location_id.id),
            ('usage', 'in', ['internal', 'customer']),
        ])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Artworks'),
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [
                ('current_location_id', 'in', child_locations.ids),
                ('product_type', '=', 'artwork'),
                '|', ('company_id', '=', False),
                     ('company_id', '=', self.company_id.id),
            ],
        }
