from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    psa_content_top = fields.Html(string='Pre-Sale Advice — Top')
    psa_content_bottom = fields.Html(string='Pre-Sale Advice — Bottom')
    posa_content_top = fields.Html(string='Post-Sale Advice — Top')
    posa_content_bottom = fields.Html(string='Post-Sale Advice — Bottom')
    vss_content_top = fields.Html(string='Vendor Settlement — Top')
    vss_content_bottom = fields.Html(string='Vendor Settlement — Bottom')

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            self.env['ir.sequence'].sudo().create({
                'name': f'SOR Vendor Settlement Statement ({company.name})',
                'code': 'sor.vendor.settlement',
                'padding': 6,
                'number_increment': 1,
                'number_next': 100001,
                'company_id': company.id,
            })
        return companies
