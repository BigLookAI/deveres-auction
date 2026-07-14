from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SorEventAuction(models.Model):
    _inherit = 'sor.event'

    auction_subtype = fields.Selection(
        selection=[
            ('live', 'Live'),
            ('online_only', 'Online Only'),
            ('hybrid', 'Hybrid'),
        ],
        string='Auction Subtype',
        tracking=True,
    )
    sale_number = fields.Char(
        string='Sale Number',
    )
    preview_start = fields.Datetime(
        string='Preview Start',
    )
    preview_end = fields.Datetime(
        string='Preview End',
    )
    lot_ids = fields.One2many(
        comodel_name='sor.lot',
        inverse_name='auction_id',
        string='Lots',
    )
    lot_count = fields.Integer(
        compute='_compute_lot_count',
        store=False,
    )

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        for event in self:
            event.lot_count = len(event.lot_ids)

    def action_go_live(self):
        """Transition the auction event to Active and cascade catalogued lots to Live.

        Only lots in Catalogued state are transitioned. Draft lots (not yet curated
        into the catalogue) are intentionally excluded. The state write bypasses the
        lot's own action method because `live` is a bridge-only state introduced by
        selection_add — no corresponding action method exists on the base sor.lot model.
        """
        for event in self:
            if event.status != 'published':
                raise UserError(
                    _('Only a Published auction can be opened. '
                      'Auction "%s" is currently %s.')
                    % (event.name, dict(self._fields['status'].selection)[event.status]),
                )
            draft_lots = event.lot_ids.filtered(lambda lot: lot.state == 'draft')
            if draft_lots:
                raise UserError(_(
                    "%(count)d lot(s) are still in Draft state. "
                    "Catalogue all lots before going live.",
                    count=len(draft_lots),
                ))
            event.status = 'active'
            event.message_post(body=_('Auction opened — Go Live triggered.'))
            catalogued_lots = event.lot_ids.filtered(
                lambda lot: lot.state == 'catalogued',
            )
            if catalogued_lots:
                catalogued_lots.write({'state': 'live'})
                event.message_post(
                    body=_('%d lot(s) transitioned to Live.') % len(catalogued_lots),
                )
