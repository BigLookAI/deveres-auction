# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    external_location_ids = fields.One2many(
        'stock.location',
        'contact_id',
        string='External Location Records',
        domain=[('usage', '=', 'customer')],
    )
    external_location_count = fields.Integer(
        string='External Locations',
        compute='_compute_external_location_count',
    )

    def _compute_external_location_count(self):
        StockLocation = self.env['stock.location']
        company_id = self.env.company.id
        for partner in self:
            partner.external_location_count = StockLocation.search_count([
                ('contact_id', '=', partner.id),
                ('usage', '=', 'customer'),
                ('company_id', '=', company_id),
            ])

    def action_open_external_locations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('External Locations'),
            'res_model': 'stock.location',
            'view_mode': 'list,form',
            'domain': [
                ('contact_id', '=', self.id),
                ('usage', '=', 'customer'),
                ('company_id', '=', self.env.company.id),
            ],
            'context': {
                'default_contact_id': self.id,
                'default_usage': 'customer',
                'sor_external_context': True,
            },
        }

    def action_create_external_location(self):
        """Open a new External Location form in a modal dialog, pre-populated from
        this contact. Raises UserError if the External Locations parent has not been
        enabled in Settings. The record is created only when the user saves the dialog.
        """
        self.ensure_one()
        parent = self.env['stock.location'].search([
            ('name', '=', 'External Locations'),
            ('usage', '=', 'view'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not parent:
            raise UserError(
                _("The External Locations feature has not been enabled. "
                  "Go to Inventory → Configuration → Settings and enable "
                  "\"External Locations\" first."),
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('New External Location'),
            'res_model': 'stock.location',
            'view_mode': 'form',
            'view_id': self.env.ref('sor_locations_external.view_external_location_form').id,
            'target': 'new',
            'context': {
                'default_contact_id': self.id,
                'default_usage': 'customer',
                'default_location_id': parent.id,
                'default_ext_street': self.street or False,
                'default_ext_city': self.city or False,
                'default_ext_zip': self.zip or False,
                'default_ext_country_id': self.country_id.id if self.country_id else False,
            },
        }
