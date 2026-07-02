from odoo import _, api, models
from odoo.exceptions import UserError

_UNIQUE_OBJECT_ERROR = (
    "Replenishment is not available for unique artwork objects. "
    "Each artwork is a unique, non-fungible object that cannot be reordered."
)


class ProductReplenish(models.TransientModel):
    _inherit = 'product.replenish'

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        tmpl_id = defaults.get('product_tmpl_id')
        if tmpl_id:
            tmpl = self.env['product.template'].browse(tmpl_id)
            if tmpl.asset_paradigm == 'unique_object':
                raise UserError(_(_UNIQUE_OBJECT_ERROR))
        return defaults

    def action_replenish(self):
        if self.product_tmpl_id.asset_paradigm == 'unique_object':
            raise UserError(_(_UNIQUE_OBJECT_ERROR))
        return super().action_replenish()
