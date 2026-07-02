from odoo import fields, models


class SorLot(models.Model):
    _inherit = 'sor.lot'

    pre_sale_advice_id = fields.Many2one(
        comodel_name='sor.pre.sale.advice',
        string='Pre-Sale Advice',
        copy=False,
    )
    post_sale_advice_id = fields.Many2one(
        comodel_name='sor.post.sale.advice',
        string='Post-Sale Advice',
        copy=False,
    )
    vendor_settlement_id = fields.Many2one(
        comodel_name='sor.vendor.settlement',
        string='Vendor Settlement',
        copy=False,
    )
