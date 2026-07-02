from odoo import api, fields, models

_TYPE_NAMES = {
    'incoming': 'Movement In',
    'outgoing': 'Movement Out',
    'internal': 'Internal Transfers',
}
_STATE_LABELS = {
    ('incoming', 'queued'): 'Queued',
    ('incoming', 'confirmed'): 'Received',
    ('incoming', 'cancelled'): 'Cancelled',
    ('outgoing', 'queued'): 'Queued',
    ('outgoing', 'confirmed'): 'Dispatched',
    ('outgoing', 'cancelled'): 'Cancelled',
    ('internal', 'queued'): 'Queued',
    ('internal', 'confirmed'): 'Transferred',
    ('internal', 'cancelled'): 'Cancelled',
}


class SorTrackingDashboard(models.TransientModel):
    _name = 'sor.tracking.dashboard'
    _description = 'Movement Activity Dashboard'

    name = fields.Char(default='Movement Activity')

    mvi_queued = fields.Integer(compute='_compute_counts')
    mvi_confirmed = fields.Integer(compute='_compute_counts')
    mvi_cancelled = fields.Integer(compute='_compute_counts')
    mvo_queued = fields.Integer(compute='_compute_counts')
    mvo_confirmed = fields.Integer(compute='_compute_counts')
    mvo_cancelled = fields.Integer(compute='_compute_counts')
    mvt_queued = fields.Integer(compute='_compute_counts')

    @api.depends()
    def _compute_counts(self):
        self.env.cr.execute("""
            SELECT pt.code, sp.sor_movement_state, COUNT(*) AS cnt
            FROM stock_picking sp
            JOIN stock_picking_type pt ON sp.picking_type_id = pt.id
            WHERE pt.code IN ('incoming', 'outgoing', 'internal')
              AND sp.company_id = %(company_id)s
            GROUP BY pt.code, sp.sor_movement_state
        """, {'company_id': self.env.company.id})
        counts = {(row[0], row[1]): row[2] for row in self.env.cr.fetchall()}
        for rec in self:
            rec.mvi_queued = counts.get(('incoming', 'queued'), 0)
            rec.mvi_confirmed = counts.get(('incoming', 'confirmed'), 0)
            rec.mvi_cancelled = counts.get(('incoming', 'cancelled'), 0)
            rec.mvo_queued = counts.get(('outgoing', 'queued'), 0)
            rec.mvo_confirmed = counts.get(('outgoing', 'confirmed'), 0)
            rec.mvo_cancelled = counts.get(('outgoing', 'cancelled'), 0)
            rec.mvt_queued = counts.get(('internal', 'queued'), 0)

    @api.model
    def _picking_action(self, type_code, state):
        label = _STATE_LABELS.get((type_code, state), state.title())
        name = f"{_TYPE_NAMES[type_code]} — {label}"
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [
                ('picking_type_id.code', '=', type_code),
                ('sor_movement_state', '=', state),
            ],
        }

    @api.model
    def action_view_mvi_queued(self, *args):
        return self._picking_action('incoming', 'queued')

    @api.model
    def action_view_mvi_confirmed(self, *args):
        return self._picking_action('incoming', 'confirmed')

    @api.model
    def action_view_mvi_cancelled(self, *args):
        return self._picking_action('incoming', 'cancelled')

    @api.model
    def action_view_mvo_queued(self, *args):
        return self._picking_action('outgoing', 'queued')

    @api.model
    def action_view_mvo_confirmed(self, *args):
        return self._picking_action('outgoing', 'confirmed')

    @api.model
    def action_view_mvo_cancelled(self, *args):
        return self._picking_action('outgoing', 'cancelled')

    @api.model
    def action_view_mvt_queued(self, *args):
        return self._picking_action('internal', 'queued')
