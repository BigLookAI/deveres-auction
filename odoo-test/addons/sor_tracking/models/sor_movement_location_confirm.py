from odoo import _, fields, models


class SorMovementLocationConfirm(models.TransientModel):
    _name = 'sor.movement.location.confirm'
    _description = 'Movement Location Update Confirmation'

    picking_id = fields.Many2one('stock.picking', string='Movement', required=True)

    def action_open(self):
        return {
            'name': _('Confirm Location Update'),
            'type': 'ir.actions.act_window',
            'res_model': 'sor.movement.location.confirm',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        return self.picking_id.with_context(sor_skip_location_confirm=True).button_validate()
