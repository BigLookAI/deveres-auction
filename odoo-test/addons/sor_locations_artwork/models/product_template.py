# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    current_location_id = fields.Many2one(
        'stock.location',
        string='Current Location',
        domain="[('usage', 'in', ['internal', 'customer', 'supplier']), ('company_id', '!=', False)]",
        check_company=True,
        tracking=True,
        help="The physical location where this artwork is currently held. "
             "Covers Rooms (internal), Studios (internal), and External locations (customer). "
             "Provided by the sor_locations_artwork bridge module — absent when either "
             "sor_locations or sor_artwork is not installed.",
    )
