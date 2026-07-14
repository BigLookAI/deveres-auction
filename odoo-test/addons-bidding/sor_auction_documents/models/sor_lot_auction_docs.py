from odoo import fields, models


class SorLot(models.Model):
    _inherit = 'sor.lot'

    consignor_company = fields.Char(
        string='Consignor Company',
    )
    sor_receipt_number = fields.Char(
        string='Receipt No',
    )
    vat_margin_scheme = fields.Boolean(
        string='VAT Margin Scheme',
        default=lambda self: self.env.company.vat_margin_scheme,
        help=(
            'When enabled, the hammer price is treated as VAT-inclusive under the margin scheme. '
            'PDF documents display the hammer price with an M- annotation and VAT as €0.00. '
            'Defaults from the company setting; override per lot as needed.'
        ),
    )
