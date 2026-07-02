from odoo import api, fields, models


class SorLotCommercial(models.Model):
    _inherit = 'sor.lot'

    is_commercial_auction = fields.Boolean(
        compute='_compute_is_commercial_auction',
        store=False,
    )
    sellers_commission_pct = fields.Float(string="Seller's Commission %", digits=(10, 1))
    withdrawal_fee_pct = fields.Float(
        string='Withdrawal Fee %',
        digits=(10, 1),
        help=(
            'Fee charged to the consignor if this lot is withdrawn before sale. '
            'Does not affect the break-even value.'
        ),
    )
    buyers_premium_pct = fields.Float(string="Buyer's Premium %", digits=(10, 1))

    @api.depends('auction_id', 'auction_id.is_commercial', 'company_id.business_model')
    def _compute_is_commercial_auction(self):
        for lot in self:
            if lot.auction_id:
                lot.is_commercial_auction = lot.auction_id.is_commercial
            else:
                lot.is_commercial_auction = lot.company_id.business_model == 'auction_house'

    @api.depends('reserve_price', 'sellers_commission_pct')
    def _compute_break_even_value(self):
        for lot in self:
            commission = lot.sellers_commission_pct or 0.0
            if 0.0 < commission < 100.0:
                lot.break_even_value = (lot.reserve_price or 0.0) / (1.0 - commission / 100.0)
            else:
                lot.break_even_value = lot.reserve_price or 0.0

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        company = self.env.company

        # Seller's commission: company fee schedule entry
        if 'sellers_commission_pct' in fields_list:
            fee = company.fee_default_ids.filtered(
                lambda f: f.fee_type == 'sellers_commission',
            )
            defaults['sellers_commission_pct'] = fee.rate_pct if fee else 0.0

        # Withdrawal fee: company fee schedule entry
        if 'withdrawal_fee_pct' in fields_list:
            fee = company.fee_default_ids.filtered(
                lambda f: f.fee_type == 'withdrawal_fee',
            )
            defaults['withdrawal_fee_pct'] = fee.rate_pct if fee else 0.0

        # Buyer's premium: first (lowest sequence) tier rate
        if 'buyers_premium_pct' in fields_list:
            tier = company.buyers_premium_tier_ids.sorted('sequence')[:1]
            defaults['buyers_premium_pct'] = tier.rate_pct if tier else 0.0

        return defaults
