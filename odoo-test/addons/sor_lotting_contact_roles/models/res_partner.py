from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    consigned_lot_count = fields.Integer(
        compute='_compute_consigned_lot_count',
        store=False,
        string='Consigned Lot Count',
    )
    consigned_lot_ids = fields.One2many(
        comodel_name='sor.lot',
        inverse_name='consignor_id',
        string='Consigned Lots',
        domain=lambda self: [('company_id', '=', self.env.company.id)],
    )

    @api.depends()
    def _compute_consigned_lot_count(self):
        for partner in self:
            partner.consigned_lot_count = self.env['sor.lot'].search_count([
                ('consignor_id', '=', partner.id),
                ('company_id', '=', self.env.company.id),
            ])

    def action_view_consigned_lots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Consigned Lots',
            'res_model': 'sor.lot',
            'view_mode': 'list,form',
            'domain': [
                ('consignor_id', '=', self.id),
                ('company_id', '=', self.env.company.id),
            ],
            'context': {'default_consignor_id': self.id},
        }
