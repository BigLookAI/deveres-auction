# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sor_external_locations_enabled = fields.Boolean(
        string='External Locations',
        config_parameter='sor_locations.external_locations_enabled',
        help="Track artworks held at specific external (customer) locations linked to contacts. "
             "Creates an \"External Locations\" parent for this company when enabled.",
    )

    def set_values(self):
        super().set_values()
        enabled = self.sor_external_locations_enabled
        # Show/hide the External Locations menu based on the setting.
        menu = self.env.ref(
            'sor_locations_external.menu_external_locations',
            raise_if_not_found=False,
        )
        if menu:
            menu.active = enabled
        if enabled:
            self.env['stock.location']._sor_ensure_external_locations_parent()
