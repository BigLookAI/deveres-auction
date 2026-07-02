from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    auction_sale_terms = fields.Html(
        string='Auction Sale Terms',
    )
    auction_bank_details = fields.Text(
        string='Bank Account Details',
        help='Bank details printed on Vendor Settlement Statements.',
    )
    auction_licence_ref = fields.Char(
        string='Auction Licence Reference',
        help='e.g. PSRA Licence No. 002261 — rendered in PDF footer.',
    )
    auction_director_signature = fields.Text(
        string='Director Signature',
        help='e.g. Rory Guthrie, Director — rendered as sign-off block in PDFs.',
    )

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
