from odoo import fields, models


class SorLotFixedCharge(models.Model):
    _name = 'sor.lot.fixed.charge'
    _description = 'Lot Fixed Charge'

    lot_id = fields.Many2one('sor.lot', required=True, ondelete='cascade')
    charge_type_id = fields.Many2one('sor.fixed.charge.type', required=True)
    amount = fields.Monetary(currency_field='currency_id')
    # currency_id and company_id always track the parent lot — not independently
    # settable, so the required=True + default=env.company pattern for company_id
    # in sor_multi_company.md does not apply here.
    currency_id = fields.Many2one(related='lot_id.currency_id', store=True)
    company_id = fields.Many2one(related='lot_id.company_id', store=True, readonly=True)
