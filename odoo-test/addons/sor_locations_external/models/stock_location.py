# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    def _sor_ensure_external_locations_parent(self):
        """Return the External Locations view location for the current company,
        creating it if absent. Idempotent — returns the existing record if
        already present.
        """
        company = self.env.company
        parent = self.search([
            ('name', '=', 'External Locations'),
            ('usage', '=', 'view'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not parent:
            parent = self.create({
                'name': 'External Locations',
                'usage': 'view',
                'company_id': company.id,
            })
        return parent

    @api.model
    def default_get(self, fields_list):
        """Pre-populate location_id with the External Locations view location when
        creating a new external location (identified by sor_external_context in context).
        """
        defaults = super().default_get(fields_list)
        if 'location_id' in fields_list and self.env.context.get('sor_external_context'):
            parent = self.search([
                ('name', '=', 'External Locations'),
                ('usage', '=', 'view'),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            if parent:
                defaults['location_id'] = parent.id
        return defaults

    contact_id = fields.Many2one(
        'res.partner',
        string='Customer Contact',
        domain=[('is_contact', '=', True)],
        help="The customer contact whose premises this location represents.",
    )
    # Independent stored fields — not related/computed. Defaulted via onchange
    # when contact_id is first selected; freely editable after that.
    # Multiple external locations per contact with distinct addresses is fully supported.
    ext_street = fields.Char(string='Street')
    ext_city = fields.Char(string='City')
    ext_zip = fields.Char(string='ZIP / Postcode')
    ext_country_id = fields.Many2one('res.country', string='Country')

    @api.onchange('contact_id')
    def _onchange_contact_id_address(self):
        """Default address fields from the customer contact when first selected.
        Fields are independently editable and persist after the contact is changed.
        """
        if self.contact_id:
            self.ext_street = self.contact_id.street
            self.ext_city = self.contact_id.city
            self.ext_zip = self.contact_id.zip
            self.ext_country_id = self.contact_id.country_id
