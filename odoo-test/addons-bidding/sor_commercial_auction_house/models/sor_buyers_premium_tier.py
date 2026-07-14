from odoo import fields, models


class SorBuyersPremiumTier(models.Model):
    _name = 'sor.buyers.premium.tier'
    _description = 'SOR Buyers Premium Tier'
    _order = 'company_id, sequence'
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
    )
    sequence = fields.Integer(default=10)
    threshold_from = fields.Monetary(
        string='Hammer Price From',
        currency_field='currency_id',
        help=(
            "Buyer's premium at this rate applies when the hammer price is at or above "
            "this amount. Use 0.00 for the base tier (applies to all hammer prices)."
        ),
    )
    rate_pct = fields.Float(string='Rate %', digits=(10, 1))
