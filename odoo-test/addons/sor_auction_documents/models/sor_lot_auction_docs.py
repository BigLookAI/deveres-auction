from odoo import fields, models


class SorLot(models.Model):
    _inherit = 'sor.lot'

    consignor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Consignor',
        check_company=True,
    )
    hammer_price_vat_included = fields.Boolean(
        string='Hammer Price VAT Included',
        default=lambda self: self.env.company.hammer_price_vat_included,
        help=(
            'When enabled, the hammer price is treated as VAT-inclusive under the margin scheme. '
            'PDF documents display the hammer price with an M- annotation and VAT as €0.00. '
            'Defaults from the company setting; override per lot as needed.'
        ),
    )
