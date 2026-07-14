from odoo import api, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            self.env['ir.sequence'].create({
                'name': f'SOR Lot ({company.name})',
                'code': 'sor.lot',
                'prefix': 'LOT/%(year)s/',
                'padding': 5,
                'number_increment': 1,
                'number_next': 1,
                'company_id': company.id,
            })
        return companies
