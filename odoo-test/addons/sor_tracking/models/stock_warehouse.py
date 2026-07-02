from odoo import api, models

from odoo.addons.sor_tracking.hooks import _ensure_pool_locations


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        for warehouse in warehouses:
            _ensure_pool_locations(self.env, warehouse.company_id)
        return warehouses
