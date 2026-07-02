# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, models
from odoo.exceptions import UserError


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        for warehouse in warehouses:
            if warehouse.code != 'AS':  # recursion guard
                self.sudo().with_company(warehouse.company_id)._sor_ensure_artist_studios_warehouse()
        return warehouses

    def _sor_ensure_artist_studios_warehouse(self):
        """Return the Artist Studios Warehouse for the current company,
        creating it if absent. Idempotent — returns the existing record if
        already present. Raises UserError if the company has no address.
        """
        company = self.env.company
        if not company.partner_id:
            raise UserError(
                _("Company '%s' has no address configured. "
                  "Go to Settings → Companies to add one before enabling Artist Studios.")
                % company.name,
            )
        warehouse = self.search([
            ('name', '=', 'Artist Studios'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not warehouse:
            warehouse = self.create({
                'name': 'Artist Studios',
                'code': 'AS',
                'partner_id': company.partner_id.id,
                'company_id': company.id,
            })
        return warehouse
