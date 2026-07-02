from odoo import _, api, models

REASON_LABELS = {
    'missing_serial': (
        'No intake record found for this artwork. '
        'Add this artwork to a consignment intake movement and set the movement to Ready, '
        'then try again.'
    ),
    'missing_movement': (
        'No incoming movement found for this artwork. '
        'Ensure a consignment intake movement has been created for this object.'
    ),
    'missing_consignment': (
        'An incoming movement exists but it is not linked to a Consignment In agreement. '
        'Open the movement and attach the relevant consignment agreement.'
    ),
}


class SorLot(models.Model):
    _inherit = 'sor.lot'

    def _resolve_consignor(self):
        """Traverse serial → movement → consignment agreement → consignor.

        Returns (partner, None) on success.
        Returns (False, reason_code) on failure, where reason_code is one of:
          'missing_serial'       — no stock.lot exists for the product
          'missing_movement'     — serial exists but no incoming picking found
          'missing_consignment'  — picking exists but not linked to a consignment agreement
        """
        self.ensure_one()
        if not self.product_id:
            return False, 'missing_serial'

        # sor.lot.product_id is product.template; stock.lot.product_id is product.product.
        # Resolve via product_variant_ids — artworks have exactly one variant.
        product_variants = self.product_id.product_variant_ids
        if not product_variants:
            return False, 'missing_serial'

        stock_lot = self.env['stock.lot'].search([
            ('product_id', 'in', product_variants.ids),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not stock_lot:
            return False, 'missing_serial'

        # Step 1: any incoming picking for this serial (all states)
        # Distinguishes missing_movement from missing_consignment.
        picking_any = self.env['stock.picking'].search([
            ('picking_type_id.code', '=', 'incoming'),
            ('move_line_ids.lot_id', '=', stock_lot.id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not picking_any:
            return False, 'missing_movement'

        # Step 2: most recent incoming picking linked to a consignment_in agreement.
        # date_done desc puts completed pickings first; id desc orders non-done by recency.
        picking = self.env['stock.picking'].search([
            ('picking_type_id.code', '=', 'incoming'),
            ('agreement_id', '!=', False),
            ('agreement_id.agreement_type', '=', 'consignment_in'),
            ('move_line_ids.lot_id', '=', stock_lot.id),
            ('company_id', '=', self.company_id.id),
        ], order='date_done desc, id desc', limit=1)
        if not picking:
            return False, 'missing_consignment'

        return picking.agreement_id.primary_partner_id, None

    def action_fetch_consignor(self):
        """Populate consignor_id on demand from the serial/movement/agreement chain.

        Returns a display_notification: success with partner name on resolve,
        or a sticky warning with a structured diagnostic on failure.
        """
        self.ensure_one()
        partner, reason = self._resolve_consignor()
        if partner:
            self.consignor_id = partner
            self.env['bus.bus']._sendone(
                self.env.user.partner_id,
                'simple_notification',
                {
                    'title': _('Consignor Resolved'),
                    'message': _('Consignor set to %s.') % partner.name,
                    'type': 'success',
                    'sticky': False,
                },
            )
            return False
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Consignor Not Found'),
                'message': _(REASON_LABELS.get(reason, 'Unknown error.')),
                'type': 'warning',
                'sticky': True,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for lot in records:
            if not lot.consignor_id and lot.product_id:
                partner, _reason = lot._resolve_consignor()
                if partner:
                    lot.consignor_id = partner
        return records
