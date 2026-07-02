from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def get_formview_action(self, access_uid=None):
        action = super().get_formview_action(access_uid=access_uid)
        if self.product_tmpl_id.product_type == 'artwork':
            action['res_model'] = 'product.template'
            action['res_id'] = self.product_tmpl_id.id
            action['views'] = [(False, 'form')]
        return action
