# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sor_artist_studios_enabled = fields.Boolean(
        string='Artist Studios Enabled',
        compute='_compute_sor_artist_studios_enabled',
        store=False,
    )

    def _compute_sor_artist_studios_enabled(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            'sor_locations.artist_studios_enabled', default='False',
        )
        enabled = bool(param and param.lower() not in ('false', '0', ''))
        for partner in self:
            partner.sor_artist_studios_enabled = enabled

    studio_ids = fields.One2many(
        'stock.location',
        'artist_id',
        string='Studio Locations',
        domain=[('usage', '=', 'internal')],
    )
    studio_count = fields.Integer(
        string='Studios',
        compute='_compute_studio_count',
    )

    def _compute_studio_count(self):
        StockLocation = self.env['stock.location']
        company_id = self.env.company.id
        for partner in self:
            partner.studio_count = StockLocation.search_count([
                ('artist_id', '=', partner.id),
                ('usage', '=', 'internal'),
                ('company_id', '=', company_id),
            ])

    def action_open_studios(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Studios'),
            'res_model': 'stock.location',
            'view_mode': 'list,form',
            'domain': [
                ('artist_id', '=', self.id),
                ('usage', '=', 'internal'),
                ('company_id', '=', self.env.company.id),
            ],
            'context': {
                'default_artist_id': self.id,
                'default_usage': 'internal',
            },
        }

    def action_create_studio(self):
        """Open a new Studio location form in a modal dialog, pre-populated from
        this artist contact. Raises UserError if the Artist Studios Warehouse has
        not been enabled in Settings. The record is created only when the user saves.
        """
        self.ensure_one()
        warehouse = self.env['stock.warehouse'].search([
            ('name', '=', 'Artist Studios'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not warehouse:
            raise UserError(
                _("The Artist Studios Viewing Location has not been enabled. "
                  "Go to Inventory → Configuration → Settings and enable "
                  "\"Artist Studios\" first."),
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Studio'),
            'res_model': 'stock.location',
            'view_mode': 'form',
            'view_id': self.env.ref('sor_locations_artist_studios.view_studio_form').id,
            'target': 'new',
            'context': {
                'default_artist_id': self.id,
                'default_usage': 'internal',
                'default_location_id': warehouse.view_location_id.id,
                'default_studio_street': self.street or False,
                'default_studio_city': self.city or False,
                'default_studio_zip': self.zip or False,
                'default_studio_country_id': self.country_id.id if self.country_id else False,
            },
        }
