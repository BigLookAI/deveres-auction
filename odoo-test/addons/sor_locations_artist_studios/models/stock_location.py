# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    @api.model
    def default_get(self, fields_list):
        """Pre-populate location_id with the Artist Studios view location when
        creating a new Studio (identified by sor_studio_context in context).
        """
        defaults = super().default_get(fields_list)
        if 'location_id' in fields_list and self.env.context.get('sor_studio_context'):
            warehouse = self.env['stock.warehouse'].search([
                ('name', '=', 'Artist Studios'),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            if warehouse:
                defaults['location_id'] = warehouse.view_location_id.id
        return defaults

    artist_id = fields.Many2one(
        'res.partner',
        string='Artist',
        domain=[('is_artist', '=', True)],
        help="The artist whose studio this location represents.",
    )
    # Independent stored fields — not related/computed. Defaulted via onchange
    # when artist_id is first selected; freely editable after that.
    # Multiple studios per artist with distinct addresses is fully supported.
    studio_street = fields.Char(string='Street')
    studio_city = fields.Char(string='City')
    studio_zip = fields.Char(string='ZIP / Postcode')
    studio_country_id = fields.Many2one('res.country', string='Country')

    @api.onchange('artist_id')
    def _onchange_artist_id_address(self):
        """Default address fields from the artist contact when first selected.
        Fields are independently editable and persist after the artist is changed.
        """
        if self.artist_id:
            self.studio_street = self.artist_id.street
            self.studio_city = self.artist_id.city
            self.studio_zip = self.artist_id.zip
            self.studio_country_id = self.artist_id.country_id
