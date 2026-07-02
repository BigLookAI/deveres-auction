from odoo import _, models

from .sor_lot_consignment_auction import REASON_LABELS


class SorEvent(models.Model):
    _inherit = 'sor.event'

    def _resolve_consignors_for_event(self):
        """Populate consignor_id on all lots in this event via the traversal chain.

        Skips lots that already have consignor_id set.

        Returns:
            {
                'resolved': <recordset of lots with consignor_id now set>,
                'unresolved': [
                    {'lot': lot, 'ref': lot.lot_reference, 'reason': reason_code},
                    ...
                ],
            }
        """
        self.ensure_one()
        resolved = self.env['sor.lot'].browse()
        unresolved = []

        for lot in self.lot_ids:
            if lot.consignor_id:
                resolved |= lot
                continue
            partner, reason = lot._resolve_consignor()
            if partner:
                lot.consignor_id = partner
                resolved |= lot
            else:
                unresolved.append({
                    'lot': lot,
                    'ref': lot.lot_reference or f'Lot {lot.id}',
                    'reason': reason,
                })

        return {'resolved': resolved, 'unresolved': unresolved}

    def _format_consignor_diagnostic(self, unresolved):
        """Format unresolved lot entries as a user-facing warning string."""
        lines = [_('The following lots could not be assigned a consignor:')]
        for entry in unresolved:
            label = _(REASON_LABELS.get(entry['reason'], entry['reason']))
            lines.append(f"• {entry['ref']}: {label}")
        return '\n'.join(lines)

    def _notify_consignor_gaps(self, unresolved):
        """Send a sticky bus notification listing unresolvable lots."""
        if not unresolved:
            return
        self.env['bus.bus']._sendone(
            self.env.user.partner_id,
            'simple_notification',
            {
                'title': _('Some lots could not be assigned a consignor'),
                'message': self._format_consignor_diagnostic(unresolved),
                'type': 'warning',
                'sticky': True,
            },
        )

    def action_generate_pre_sale_advices(self):
        result = self._resolve_consignors_for_event()
        self._notify_consignor_gaps(result['unresolved'])
        return super().action_generate_pre_sale_advices()

    def action_generate_post_sale_advices(self):
        result = self._resolve_consignors_for_event()
        self._notify_consignor_gaps(result['unresolved'])
        return super().action_generate_post_sale_advices()

    def action_generate_vendor_settlements(self):
        result = self._resolve_consignors_for_event()
        self._notify_consignor_gaps(result['unresolved'])
        return super().action_generate_vendor_settlements()
