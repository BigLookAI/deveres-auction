from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.depends('name', 'default_code')
    @api.depends_context('formatted_display_name', 'suppress_product_code')
    def _compute_display_name(self):
        if self.env.context.get('suppress_product_code'):
            for template in self:
                template.display_name = template.name or False
        else:
            super()._compute_display_name()
