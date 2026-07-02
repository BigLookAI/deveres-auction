from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # Mirror template-level suppression booleans so variant form views
    # can use them directly without chained-field invisible expressions.
    is_forecast_btn_suppressed = fields.Boolean(
        related='product_tmpl_id.is_forecast_btn_suppressed', store=False)
    is_reorder_btn_suppressed = fields.Boolean(
        related='product_tmpl_id.is_reorder_btn_suppressed', store=False)
    is_moves_btn_suppressed = fields.Boolean(
        related='product_tmpl_id.is_moves_btn_suppressed', store=False)
    is_putaway_btn_suppressed = fields.Boolean(
        related='product_tmpl_id.is_putaway_btn_suppressed', store=False)
    is_storage_cap_btn_suppressed = fields.Boolean(
        related='product_tmpl_id.is_storage_cap_btn_suppressed', store=False)
    is_qty_column_suppressed = fields.Boolean(
        related='product_tmpl_id.is_qty_column_suppressed', store=False)
