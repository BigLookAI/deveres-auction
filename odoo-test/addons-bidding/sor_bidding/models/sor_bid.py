from odoo import api, fields, models


class SorBid(models.Model):
    _name = 'sor.bid'
    _description = 'SOR Bid'
    _order = 'bid_datetime desc'
    _check_company_auto = True

    lot_id = fields.Many2one(
        comodel_name='sor.lot',
        string='Lot',
        required=True,
        ondelete='cascade',
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='lot_id.company_id',
        store=True,
        string='Company',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='lot_id.currency_id',
        store=True,
        string='Currency',
    )
    bidder_id = fields.Many2one(
        comodel_name='res.partner',
        string='Bidder',
        required=True,
        context={'search_default_filter_contacts': 1},
    )
    bid_type = fields.Selection(
        selection=[
            ('floor', 'Floor'),
            ('absentee', 'Absentee'),
            ('commission', 'Commission'),
            ('online', 'Online'),
            ('phone', 'Phone'),
        ],
        string='Bid Type',
        required=True,
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
    )
    max_amount = fields.Monetary(
        string='Maximum',
        currency_field='currency_id',
        help=(
            'Maximum ceiling for commission bids — '
            'auctioneer bids up to this amount on behalf of the absent bidder.'
        ),
    )
    bid_datetime = fields.Datetime(
        string='Bid Date/Time',
        default=fields.Datetime.now,
        required=True,
    )
    external_bid_id = fields.Char(
        string='External Bid ID',
        index=True,
        help='External platform bid reference — used for idempotent import.',
    )
    is_winning_bid = fields.Boolean(
        string='Winning Bid',
        default=False,
        copy=False,
        help='Set when this bid determines the hammer price on a Sold lot. Locks the bid record.',
    )
    notes = fields.Text(
        string='Notes',
    )

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for bid in records:
            if bid.bidder_id:
                bid._assign_bidder_contact_type()
        return records

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assign_bidder_contact_type(self):
        """Auto-assign Contact parent type and Bidder sub-type to the bidder partner.

        Uses (4, id) Many2many commands so assignment is idempotent — calling this
        method multiple times for the same partner does not duplicate type records.
        """
        self.ensure_one()
        partner = self.bidder_id
        ContactType = self.env['sor.contact.type']
        contact_type = ContactType.search(
            [('code', '=', 'contact'), ('parent_type_id', '=', False)],
            limit=1,
        )
        bidder_subtype = ContactType.search(
            [('code', '=', 'bidder'), ('parent_type_id', '!=', False)],
            limit=1,
        )
        if contact_type and contact_type not in partner.contact_types:
            partner.contact_types = [(4, contact_type.id)]
        if bidder_subtype and bidder_subtype not in partner.contact_subtypes:
            partner.contact_subtypes = [(4, bidder_subtype.id)]
