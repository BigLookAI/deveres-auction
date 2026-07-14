from odoo import fields, models


class SorEventCommercial(models.Model):
    _inherit = 'sor.event'

    is_commercial = fields.Boolean(
        string='Commercial Auction',
        default=True,
        help=(
            "When enabled, buyer's premium and seller's commission apply to lots "
            "in this auction. Disable for charity or benefit auctions where no fees "
            "are charged."
        ),
    )
