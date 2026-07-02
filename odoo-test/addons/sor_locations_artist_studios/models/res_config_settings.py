# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sor_artist_studios_enabled = fields.Boolean(
        string='Artist Studios',
        config_parameter='sor_locations.artist_studios_enabled',
        help="Track artworks held at artists' studios. Creates an \"Artist Studios\" "
             "Viewing Location for this company when enabled.",
    )

    def set_values(self):
        if not self.sor_artist_studios_enabled:
            as_warehouses = self.env['stock.warehouse'].search([
                ('code', '=', 'AS'),
                ('company_id', '=', self.env.company.id),
            ])
            if as_warehouses:
                as_location_ids = self.env['stock.location'].search([
                    ('location_id', 'child_of', as_warehouses.view_location_id.ids),
                ]).ids
                occupied = self.env['stock.quant'].search_count([
                    ('location_id', 'in', as_location_ids),
                    ('quantity', '>', 0),
                ])
                if occupied:
                    raise UserError(_(
                        "Artist Studios cannot be disabled for %(company)s — "
                        "%(count)d Artist Studio location(s) currently hold stock. "
                        "Move all stock out of Artist Studio locations before disabling.",
                        company=self.env.company.name, count=occupied,
                    ))
        super().set_values()
        if self.sor_artist_studios_enabled:
            self.env['stock.warehouse']._sor_ensure_artist_studios_warehouse()
