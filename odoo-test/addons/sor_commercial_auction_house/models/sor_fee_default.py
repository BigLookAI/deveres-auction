from odoo import fields, models


class SorFeeDefault(models.Model):
    _name = 'sor.fee.default'
    _description = 'SOR Fee Default'
    _order = 'company_id, fee_type'
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    fee_type = fields.Selection(
        selection=[
            ('sellers_commission', "Seller's Commission"),
            ('withdrawal_fee', "Withdrawal Fee"),
        ],
        string='Fee Type',
        required=True,
    )
    rate_pct = fields.Float(string='Rate %', digits=(10, 1))
