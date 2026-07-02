from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_open_picking_modal(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Movement'),
            'res_model': 'stock.picking',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_link_to_agreement(self):
        """Link this picking to the agreement in context and close the dialog.

        Called from the "Link to Agreement" button in the picking selection
        dialog opened by action_link_existing_intake / action_link_existing_release.
        Reads default_agreement_id from context, validates, writes agreement_id,
        and returns act_window_close to dismiss the dialog.
        """
        self.ensure_one()
        agreement_id = self.env.context.get('default_agreement_id')
        if not agreement_id:
            raise UserError(_('No agreement context found. Please open this dialog from an agreement form.'))
        agreement = self.env['sor.agreement'].browse(agreement_id)
        if not agreement.exists():
            raise UserError(_('Agreement not found.'))
        self.agreement_id = agreement
        agreement.invalidate_recordset(['picking_ids', 'move_ids', 'picking_count'])
        return {'type': 'ir.actions.act_window_close'}

    def unlink(self):
        for picking in self:
            if picking.agreement_id:
                raise UserError(_(
                    'Cannot delete movement "%s": it is linked to agreement "%s". '
                    'Unlink the movement from the agreement first.',
                    picking.name,
                    picking.agreement_id.name,
                ))
        return super().unlink()

    def _action_done(self):
        result = super()._action_done()
        for picking in self.filtered(
            lambda p: p.agreement_id
            and p.agreement_id.agreement_type == 'consignment_out'
            and p.agreement_id.source_consignment_id,
        ):
            picking.agreement_id.source_consignment_id.invalidate_recordset(
                ['sor_compound_status'],
            )
        return result


class StockMove(models.Model):
    _inherit = 'stock.move'

    def action_open_product_modal(self):
        """Open the product template form in a modal.

        Used in the Product Lines list on the consignment agreement form
        to provide SOR Design Pattern #1: product line click opens the product.
        Navigates from stock.move.product_id (product.product) to product.template.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Product'),
            'res_model': 'product.template',
            'res_id': self.product_id.product_tmpl_id.id,
            'view_mode': 'form',
            'target': 'new',
        }
