from odoo import _, fields, models
from odoo.exceptions import UserError


class SorLotAuction(models.Model):
    _inherit = 'sor.lot'

    auction_id = fields.Many2one(
        comodel_name='sor.event',
        string='Auction',
        check_company=True,
        ondelete='restrict',
        domain=[('event_type', '=', 'auction')],
    )

    state = fields.Selection(
        selection_add=[('live', 'Live')],
        ondelete={'live': 'set default'},
    )

    _auction_lot_number_unique = models.Constraint(
        'UNIQUE(auction_id, lot_number)',
        'Lot number must be unique within an auction.',
    )

    def action_catalogue(self):
        for lot in self:
            if lot.auction_id and lot.auction_id.status == 'active':
                raise UserError(
                    _('Lot "%s" cannot be catalogued because its auction "%s" is already Live. '
                      'Lots cannot be added to an active auction.')
                    % (lot.lot_reference, lot.auction_id.name),
                )
        return super().action_catalogue()
