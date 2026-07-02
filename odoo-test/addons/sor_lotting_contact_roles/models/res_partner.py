from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Field names, types and the relation_field match ir_model_fields in the
    # deVeres April-test database exactly (module sor_lotting_contact_roles).
    consigned_lot_ids = fields.One2many(
        comodel_name='sor.lot',
        inverse_name='consignor_id',
        string='Consigned Lots',
    )
    consigned_lot_count = fields.Integer(
        string='Consigned Lot Count',
        compute='_compute_consigned_lot_count',
    )

    def _compute_consigned_lot_count(self):
        counts = {}
        if self.ids:
            counts = dict(self.env['sor.lot']._read_group(
                [('consignor_id', 'in', self.ids)],
                groupby=['consignor_id'], aggregates=['__count']))
        for partner in self:
            partner.consigned_lot_count = counts.get(partner, 0) if partner.id else 0

    def action_view_consigned_lots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consigned Lots'),
            'res_model': 'sor.lot',
            'view_mode': 'list,form',
            'domain': [('consignor_id', '=', self.id),
                       ('company_id', '=', self.env.company.id)],
            'context': {'default_consignor_id': self.id},
        }
