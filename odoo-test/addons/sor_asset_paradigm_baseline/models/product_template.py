from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    asset_paradigm = fields.Selection(
        selection_add=[('standard', 'Standard')],
    )
