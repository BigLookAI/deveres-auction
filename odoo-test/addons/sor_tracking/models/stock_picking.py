from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sor_movement_state = fields.Selection(
        selection=[
            ('queued', 'Queued'),
            ('ready', 'Ready'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Movement State',
        default='queued',
        copy=False,
        index=True,
    )
    sor_movement_state_label = fields.Char(
        string='Movement Status',
        compute='_compute_sor_movement_state_label',
        store=False,
    )
    sor_movement_hint = fields.Char(
        string='Movement Hint',
        compute='_compute_sor_movement_hint',
        store=False,
    )

    @api.depends('sor_movement_state', 'picking_type_id.code')
    def _compute_sor_movement_state_label(self):
        for picking in self:
            state = picking.sor_movement_state
            code = picking.picking_type_id.code if picking.picking_type_id else False
            if state == 'queued':
                picking.sor_movement_state_label = _('Queued')
            elif state == 'ready':
                picking.sor_movement_state_label = _('Ready')
            elif state == 'cancelled':
                picking.sor_movement_state_label = _('Cancelled')
            elif state == 'confirmed' and code == 'incoming':
                picking.sor_movement_state_label = _('Received')
            elif state == 'confirmed' and code == 'outgoing':
                picking.sor_movement_state_label = _('Dispatched')
            elif state == 'confirmed' and code == 'internal':
                picking.sor_movement_state_label = _('Transferred')
            else:
                picking.sor_movement_state_label = _('Confirmed')

    @api.depends('sor_movement_state', 'picking_type_id.code')
    def _compute_sor_movement_hint(self):
        for picking in self:
            state = picking.sor_movement_state
            code = picking.picking_type_id.code if picking.picking_type_id else False
            if state not in ('queued', 'ready'):
                picking.sor_movement_hint = ''
                continue
            if state == 'ready':
                picking.sor_movement_hint = _(
                    'This movement is staged. Validate it once items have been '
                    'physically processed.',
                )
                continue
            if code == 'incoming':
                picking.sor_movement_hint = _(
                    'This movement is queued. Confirm it once the items have been '
                    'physically received and checked in.',
                )
            elif code == 'outgoing':
                picking.sor_movement_hint = _(
                    'This movement is queued. Confirm it once the items have been '
                    'packed and dispatched to the partner.',
                )
            elif code == 'internal':
                picking.sor_movement_hint = _(
                    'This movement is queued. Confirm it once the internal '
                    'transfer has been completed.',
                )
            else:
                picking.sor_movement_hint = _(
                    'This movement is queued. Confirm it once it has been completed.',
                )

    def _sor_infer_picking_type_id(self, location_id, location_dest_id):
        """Return the inferred picking type ID for the given location IDs, or False.

        Server-side mirror of the onchange inference logic. Called from create() and
        write() because picking_type_id is readonly in the view and Odoo 19's OWL
        framework does not send static readonly field values in save payloads.
        """
        if not location_id or not location_dest_id:
            return False
        src = self.env['stock.location'].browse(location_id)
        dst = self.env['stock.location'].browse(location_dest_id)
        src_external = src.usage in ('supplier', 'customer')
        dst_external = dst.usage in ('supplier', 'customer')
        if src_external and dst_external:
            return False
        if src_external and not dst_external:
            code = 'incoming'
            warehouse = self.env['stock.warehouse'].search(
                [('lot_stock_id', 'child_of', dst.id), ('company_id', '=', dst.company_id.id)],
                limit=1,
            ) or self.env['stock.warehouse'].search(
                [('company_id', '=', dst.company_id.id or self.env.company.id)], limit=1,
            )
        elif not src_external and dst_external:
            code = 'outgoing'
            warehouse = self.env['stock.warehouse'].search(
                [('lot_stock_id', 'child_of', src.id), ('company_id', '=', src.company_id.id)],
                limit=1,
            ) or self.env['stock.warehouse'].search(
                [('company_id', '=', src.company_id.id or self.env.company.id)], limit=1,
            )
        else:
            code = 'internal'
            warehouse = self.env['stock.warehouse'].search(
                [('lot_stock_id', 'child_of', dst.id), ('company_id', '=', dst.company_id.id)],
                limit=1,
            ) or self.env['stock.warehouse'].search(
                [('company_id', '=', dst.company_id.id or self.env.company.id)], limit=1,
            )
        if not warehouse:
            return False
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', code), ('warehouse_id', '=', warehouse.id)],
            limit=1,
        )
        return picking_type.id if picking_type else False

    def _sor_infer_partner_id(self, location_id, location_dest_id):
        """Return partner_id inferred from location's linked contact, or False.

        Checks source location first (incoming/internal), then destination (outgoing).
        Reads contact_id (sor_locations_external) and artist_id (sor_locations_artist_studios).
        Returns False gracefully when neither bridge is installed.
        """
        loc_fields = self.env['stock.location']._fields
        has_contact = 'contact_id' in loc_fields
        has_artist = 'artist_id' in loc_fields
        if not has_contact and not has_artist:
            return False
        for loc_id in (location_id, location_dest_id):
            if not loc_id:
                continue
            loc = self.env['stock.location'].browse(loc_id)
            if has_contact and loc.contact_id:
                return loc.contact_id.id
            if has_artist and loc.artist_id:
                return loc.artist_id.id
        return False

    @api.onchange('location_id', 'location_dest_id')
    def _onchange_sor_infer_picking_type(self):
        # Infer partner from whichever location has a partner linked (source first,
        # then destination). Only auto-populate when staff have not set a partner yet.
        if not self.partner_id:
            inferred_partner = self._sor_infer_partner_id(
                self.location_id.id if self.location_id else False,
                self.location_dest_id.id if self.location_dest_id else False,
            )
            if inferred_partner:
                self.partner_id = inferred_partner

        if not self.location_id or not self.location_dest_id:
            return None
        src_external = self.location_id.usage in ('supplier', 'customer')
        dst_external = self.location_dest_id.usage in ('supplier', 'customer')
        if src_external and dst_external:
            return {'warning': {
                'title': _('Invalid Location Combination'),
                'message': _(
                    'Both source and destination are external locations. '
                    'A movement must involve at least one internal gallery location.',
                ),
            }}
        src = self.location_id
        dst = self.location_dest_id
        picking_type_id = self._sor_infer_picking_type_id(src.id, dst.id)
        if picking_type_id:
            self.picking_type_id = picking_type_id
            # Restore user's location selections — setting picking_type_id triggers
            # Odoo's native _onchange_picking_type which resets both locations to the
            # operation type's defaults, overwriting the user's choices.
            self.location_id = src
            self.location_dest_id = dst
        return None

    @api.model_create_multi
    def create(self, vals_list):
        # picking_type_id is readonly in the SOR view — Odoo 19's OWL framework does
        # not send static readonly field values in create payloads. Infer server-side
        # from locations so the required field is always set.
        for vals in vals_list:
            if not vals.get('picking_type_id') and vals.get('location_id') and vals.get('location_dest_id'):
                inferred = self._sor_infer_picking_type_id(
                    vals['location_id'], vals['location_dest_id'],
                )
                if inferred:
                    vals['picking_type_id'] = inferred
            if not vals.get('partner_id') and (vals.get('location_id') or vals.get('location_dest_id')):
                inferred_partner = self._sor_infer_partner_id(
                    vals.get('location_id'), vals.get('location_dest_id'),
                )
                if inferred_partner:
                    vals['partner_id'] = inferred_partner
        return super().create(vals_list)

    def write(self, vals):
        if 'sor_movement_state' in vals:
            new_state = vals['sor_movement_state']
            for picking in self:
                current = picking.sor_movement_state
                if not self._sor_movement_state_transition_allowed(
                    current, new_state,
                ):
                    raise UserError(
                        _(
                            'Cannot transition movement from %(current)s to %(new)s.',
                            current=current,
                            new=new_state,
                        ),
                    )
        # Re-infer picking_type_id when locations change without it — same OWL
        # readonly payload issue as create().
        if (vals.get('location_id') or vals.get('location_dest_id')) and not vals.get('picking_type_id'):
            for picking in self:
                location_id = vals.get('location_id', picking.location_id.id)
                location_dest_id = vals.get('location_dest_id', picking.location_dest_id.id)
                inferred = picking._sor_infer_picking_type_id(location_id, location_dest_id)
                if inferred:
                    vals = dict(vals, picking_type_id=inferred)
                    break
        return super().write(vals)

    def _sor_movement_state_transition_allowed(self, from_state, to_state):
        allowed = {
            'queued': {'ready', 'cancelled'},
            'ready': {'confirmed', 'cancelled'},
            'confirmed': set(),
            'cancelled': set(),
        }
        return to_state in allowed.get(from_state, set())

    def _get_source_location_discrepancies(self):
        if 'current_location_id' not in self.env['product.template']._fields:
            return self.env['stock.move'].browse()
        return self.move_ids.filtered(
            lambda m: m.product_id.current_location_id
            and m.location_id != m.product_id.current_location_id,
        )

    def button_validate(self):
        self.ensure_one()
        # Source location discrepancy check — skipped when the source wizard has already
        # been confirmed (skip_source_location_check) or the destination wizard confirmed
        # (sor_skip_location_confirm, which implies the user has already proceeded past both)
        if not (self.env.context.get('skip_source_location_check')
                or self.env.context.get('sor_skip_location_confirm')):
            discrepant_moves = self._get_source_location_discrepancies()
            if discrepant_moves:
                info_lines = [
                    f"• {m.product_id.display_name} — "
                    f"Recorded: {m.product_id.current_location_id.display_name}. "
                    f"Declared source: {m.location_id.display_name}"
                    for m in discrepant_moves
                ]
                wizard = self.env['sor.movement.source.location.confirm'].create({
                    'picking_id': self.id,
                    'discrepancy_info': '\n'.join(info_lines),
                })
                return {
                    'name': _('Source Location Discrepancy'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'sor.movement.source.location.confirm',
                    'res_id': wizard.id,
                    'view_mode': 'form',
                    'target': 'new',
                }
        # Destination location update confirmation — skipped when source wizard was
        # already confirmed (skip_source_location_check) to avoid a double-confirm.
        if (self.env.context.get('sor_skip_location_confirm')
                or self.env.context.get('skip_source_location_check')):
            return super().button_validate()
        if 'current_location_id' in self.env['product.template']._fields:
            products_with_location = self.move_ids.mapped(
                'product_id.product_tmpl_id',
            ).filtered(lambda p: p.current_location_id)
            if products_with_location:
                wizard = self.env['sor.movement.location.confirm'].create({
                    'picking_id': self.id,
                })
                return wizard.action_open()
        return super().button_validate()

    def _autoconfirm_picking(self):
        # Odoo 19's _autoconfirm_picking calls stock.move._action_confirm() directly,
        # bypassing stock.picking.action_confirm(). Track queued pickings before super()
        # so we can sync sor_movement_state after the native auto-confirm fires.
        sor_queued_before = self.filtered(lambda p: p.sor_movement_state == 'queued')
        result = super()._autoconfirm_picking()
        for picking in sor_queued_before:
            if picking.state not in ('draft', 'cancel') and picking.sor_movement_state == 'queued':
                picking.write({'sor_movement_state': 'ready'})
        return result

    def action_confirm(self):
        result = super().action_confirm()
        self.filtered(
            lambda p: p.sor_movement_state == 'queued',
        ).write({'sor_movement_state': 'ready'})
        return result

    def _action_done(self):
        result = super()._action_done()
        self.filtered(
            lambda p: p.sor_movement_state in ('queued', 'ready'),
        ).write({'sor_movement_state': 'confirmed'})
        if 'current_location_id' in self.env['product.template']._fields:
            for picking in self:
                for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
                    move.product_id.product_tmpl_id.sudo().current_location_id = (
                        move.location_dest_id
                    )
        return result

    def action_cancel(self):
        result = super().action_cancel()
        self.filtered(
            lambda p: p.sor_movement_state in ('queued', 'ready'),
        ).write({'sor_movement_state': 'cancelled'})
        return result

    def unlink(self):
        non_deletable = self.filtered(
            lambda p: p.sor_movement_state != 'queued',
        )
        if non_deletable:
            raise UserError(_(
                'You can only delete movements that have not yet been staged. '
                'Movements in Ready, Confirmed, or Cancelled state cannot be deleted.',
            ))
        return super().unlink()
