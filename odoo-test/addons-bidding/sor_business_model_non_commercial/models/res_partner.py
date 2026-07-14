from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_sales_purchases_tab_suppressed = fields.Boolean(
        compute='_compute_is_sales_purchases_tab_suppressed',
        store=False,
    )

    @api.depends()
    def _compute_is_sales_purchases_tab_suppressed(self):
        business_model = self.env.company.business_model
        suppressed = bool(business_model) and bool(
            self.env['sor.business.model.rule'].search_count([
                ('business_model', '=', business_model),
                ('field_key', '=', 'sales_tab'),
                ('active', '=', True),
            ]),
        )
        for rec in self:
            rec.is_sales_purchases_tab_suppressed = suppressed
