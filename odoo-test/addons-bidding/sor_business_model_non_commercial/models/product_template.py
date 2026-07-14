from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_can_be_sold_suppressed = fields.Boolean(
        compute='_compute_business_model_suppressions',
        store=False,
    )
    is_sale_price_suppressed = fields.Boolean(
        compute='_compute_business_model_suppressions',
        store=False,
    )
    is_sales_tab_suppressed = fields.Boolean(
        compute='_compute_business_model_suppressions',
        store=False,
    )
    is_prices_tab_suppressed = fields.Boolean(
        compute='_compute_business_model_suppressions',
        store=False,
    )

    @api.depends('effective_business_model')
    def _compute_business_model_suppressions(self):
        for rec in self:
            rec.is_can_be_sold_suppressed = rec.is_field_suppressed('can_be_sold')
            rec.is_sale_price_suppressed = rec.is_field_suppressed('sale_price_field')
            rec.is_sales_tab_suppressed = rec.is_field_suppressed('sales_tab')
            rec.is_prices_tab_suppressed = rec.is_field_suppressed('sale_price_tab')
