from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    auction_psra_number = fields.Char(string='PSRA Licence Number')
