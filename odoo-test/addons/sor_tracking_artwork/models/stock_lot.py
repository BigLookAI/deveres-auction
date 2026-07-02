from odoo import api, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'name' not in fields_list:
            return defaults
        product_id = self.env.context.get('default_product_id')
        if not product_id:
            return defaults
        product = self.env['product.product'].browse(product_id)
        template = product.product_tmpl_id
        if (
            template.asset_paradigm == 'unique_object'
            and template.tracking == 'serial'
        ):
            company_id = self.env.context.get('default_company_id') or self.env.company.id
            company = self.env['res.company'].browse(company_id)
            name = self.env['ir.sequence'].with_company(company).next_by_code(
                'sor.artwork.serial',
            )
            if name:
                defaults['name'] = name
        return defaults
