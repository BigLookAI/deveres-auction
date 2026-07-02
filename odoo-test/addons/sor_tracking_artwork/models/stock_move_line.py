from odoo import api, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.onchange('product_id', 'picking_id')
    def _onchange_sor_artwork_serial(self):
        for line in self:
            if (not line.lot_id
                    and not line.lot_name
                    and line.product_id
                    and line.product_id.asset_paradigm == 'unique_object'
                    and line.product_id.tracking == 'serial'):
                company = line.picking_id.company_id or self.env.company
                # BUG-18: reuse an existing lot if the artwork already has one.
                # A unique object has exactly one serial forever — creating a second
                # lot for the same product would corrupt the movement ledger.
                existing_lot = self.env['stock.lot'].search([
                    ('product_id', '=', line.product_id.id),
                    ('company_id', '=', company.id),
                ], limit=1)
                if existing_lot:
                    line.lot_id = existing_lot
                    return
                next_sn = self.env['ir.sequence'].with_company(company).next_by_code(
                    'sor.artwork.serial',
                )
                if next_sn:
                    line.lot_name = next_sn

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('lot_id') or vals.get('lot_name'):
                continue
            product_id = vals.get('product_id')
            if not product_id:
                continue
            product = self.env['product.product'].browse(product_id)
            if (product.asset_paradigm == 'unique_object'
                    and product.tracking == 'serial'):
                move_id = vals.get('move_id')
                if move_id:
                    # BUG-08: skip if the parent move already has a serial on any
                    # line. Prevents a second serial being consumed during
                    # _action_done() — done lines are new ORM objects with no
                    # lot_name at creation time, but the move already has a serial
                    # from the demand line created at action_assign() time.
                    existing_serial = self.env['stock.move.line'].search([
                        ('move_id', '=', move_id),
                        '|',
                        ('lot_name', '!=', False),
                        ('lot_id', '!=', False),
                    ], limit=1)
                    if existing_serial:
                        continue
                picking_id = vals.get('picking_id')
                company = (
                    self.env['stock.picking'].browse(picking_id).company_id
                    if picking_id else self.env.company
                )
                # BUG-18: reuse an existing lot if the artwork already has one.
                # A unique object has exactly one serial forever — creating a second
                # lot for the same product would corrupt the movement ledger.
                existing_lot = self.env['stock.lot'].search([
                    ('product_id', '=', product_id),
                    ('company_id', '=', company.id),
                ], limit=1)
                if existing_lot:
                    vals['lot_id'] = existing_lot.id
                    continue
                next_sn = self.env['ir.sequence'].with_company(company).next_by_code(
                    'sor.artwork.serial',
                )
                if next_sn:
                    picking = (
                        self.env['stock.picking'].browse(picking_id)
                        if picking_id else None
                    )
                    if picking and picking.state == 'draft':
                        # Draft: store as lot_name (Char) only — creating a stock.lot
                        # record and setting lot_id triggers Odoo's stock reservation
                        # mechanism which auto-advances the picking from draft to
                        # assigned (Ready), bypassing the "Mark as Todo" workflow.
                        # The lot_name is converted to lot_id at action_confirm().
                        vals['lot_name'] = next_sn
                    else:
                        lot = self.env['stock.lot'].sudo().create({
                            'name': next_sn,
                            'product_id': vals['product_id'],
                            'company_id': company.id,
                        })
                        vals['lot_id'] = lot.id
        return super().create(vals_list)
