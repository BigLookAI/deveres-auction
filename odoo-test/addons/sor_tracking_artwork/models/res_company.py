from odoo import api, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        # Serial tracking groups (group_stock_production_lot, group_lot_on_delivery_slip)
        # are instance-wide settings — once enabled by post_init_hook they apply to all
        # companies automatically. No per-company provisioning is required here.
        companies = super().create(vals_list)
        for company in companies:
            self.env['ir.sequence'].create({
                'name': f'SOR Artwork Serial Number ({company.name})',
                'code': 'sor.artwork.serial',
                'prefix': 'SN/%(year)s/',
                'padding': 5,
                'number_increment': 1,
                'number_next': 1,
                'company_id': company.id,
            })
        return companies
