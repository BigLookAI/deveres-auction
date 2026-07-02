# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

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
                occupied = self.env['product.template'].search_count([
                    ('current_location_id', 'in', as_location_ids),
                ])
                if occupied:
                    raise UserError(_(
                        "Artist Studios cannot be disabled for %(company)s — "
                        "%(count)d artwork(s) currently have an Artist Studio as their location. "
                        "Reassign those artworks before disabling.",
                        company=self.env.company.name, count=occupied,
                    ))
        super().set_values()
