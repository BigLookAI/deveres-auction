from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    business_model = fields.Selection(
        selection=[
            ('non_commercial', 'Non-Commercial'),
            ('primary_market_gallery', 'Primary Market Gallery'),
            ('secondary_market_gallery', 'Secondary Market Gallery'),
            ('auction_house', 'Auction House'),
        ],
        string='Business Model',
        default='non_commercial',
        required=True,
        help=(
            "Determines which commercial fee infrastructure is active for this company. "
            "Non-Commercial suppresses all pricing UI. "
            "Primary Market Gallery uses consignment revenue splits. "
            "Secondary Market Gallery uses vendor commission on resale. "
            "Auction House uses buyer's premium and seller's fee structures."
        ),
    )
