from odoo import fields, models


class SorMovementSourceLocationConfirm(models.TransientModel):
    _name = 'sor.movement.source.location.confirm'
    _description = 'Movement Source Location Confirmation'

    picking_id = fields.Many2one('stock.picking', string='Movement', required=True)
    discrepancy_info = fields.Text(string='Discrepancy Details', readonly=True)

    def action_confirm(self):
        return self.picking_id.with_context(
            skip_source_location_check=True,
        ).button_validate()

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
