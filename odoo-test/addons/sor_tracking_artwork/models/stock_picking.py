from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_confirm(self):
        draft_pickings = self.filtered(lambda p: p.state == 'draft')

        # Remove qty=0 move lines that were created by the OWL onchange when the
        # user opened Detailed Operations on a draft picking and then saved without
        # confirming. These "ghost" MLs have lot_name but no quantity — when
        # _action_confirm's internal _action_assign runs it creates a second ML
        # (qty=1) because the ghost ML contributes 0 to move.quantity. The BUG-08
        # guard then blocks serial generation on the new ML, leaving it serialless.
        # Deleting ghost MLs first lets _action_assign create one clean ML.
        ghost_mls = draft_pickings.move_line_ids.filtered(
            lambda ml: ml.lot_name and not ml.lot_id and not ml.quantity,
        )
        if ghost_mls:
            ghost_mls.sudo().unlink()

        # Convert lot_name → stock.lot → lot_id for draft artwork demand lines.
        # In Draft, create() stores the auto-assigned serial as lot_name only (not
        # lot_id) to avoid triggering Odoo's stock reservation which auto-advances
        # the picking to assigned (Ready). This conversion runs at "Mark as Todo"
        # time so the serial is locked in as a stock.lot record before Odoo
        # transitions the picking to Ready state.
        for ml in draft_pickings.move_line_ids.filtered(
            lambda ml: (
                ml.lot_name
                and not ml.lot_id
                and ml.quantity
                and ml.product_id.asset_paradigm == 'unique_object'
                and ml.product_id.tracking == 'serial'
            ),
        ):
            company = ml.picking_id.company_id or self.env.company
            lot = self.env['stock.lot'].sudo().create({
                'name': ml.lot_name,
                'product_id': ml.product_id.id,
                'company_id': company.id,
            })
            ml.sudo().write({'lot_id': lot.id, 'lot_name': False})

        # BUG-16: Pre-create stock.lot from sor_draft_lot_name BEFORE calling
        # super().action_confirm(). This ensures that when _action_assign creates
        # move lines (via the stock.move.line.create() override), it finds the
        # staff-specified lot already in the DB and reuses it — rather than
        # auto-generating a new serial which would then win the existing_lot search
        # in the post-confirm loop and override the staff intent.
        #
        # BUG-18 concern in this path: if the artwork already has a lot from a prior
        # movement, use that lot (an artwork's serial identity is permanent — the
        # staff-entered name is superseded by the existing one).
        for picking in draft_pickings:
            for move in picking.move_ids.filtered(
                lambda m: (
                    m.sor_draft_lot_name
                    and m.product_id.asset_paradigm == 'unique_object'
                    and m.product_id.tracking == 'serial'
                ),
            ):
                company = picking.company_id or self.env.company
                existing_lot = self.env['stock.lot'].search([
                    ('product_id', '=', move.product_id.id),
                    ('company_id', '=', company.id),
                ], limit=1)
                if not existing_lot:
                    existing_lot = self.env['stock.lot'].sudo().create({
                        'name': move.sor_draft_lot_name,
                        'product_id': move.product_id.id,
                        'company_id': company.id,
                    })
                # Clear now — the lot exists; _action_assign → create() override
                # will find it and use it automatically.
                move.sor_draft_lot_name = False

        result = super().action_confirm()

        # Post-confirm: for unique-object serial moves where _action_assign did not
        # create a move line (e.g. manual reservation type), create one now.
        # The stock.move.line.create() override handles lot reuse (BUG-18) and
        # auto-generates a new serial if no lot exists yet for this product.
        for picking in self:
            if picking.state in ('cancel', 'done'):
                continue
            for move in picking.move_ids.filtered(
                lambda m: (
                    m.product_id.asset_paradigm == 'unique_object'
                    and m.product_id.tracking == 'serial'
                    and m.state not in ('done', 'cancel', 'draft')
                    and not m.move_line_ids
                ),
            ):
                company = picking.company_id or self.env.company
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': 1,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': company.id,
                })

        return result
