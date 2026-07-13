from odoo import fields, models


class SorFixedChargeType(models.Model):
    _name = 'sor.fixed.charge.type'
    _description = 'Fixed Charge Type'
    _order = 'sequence, name'

    # No company_id — this is a global registry shared across all companies,
    # per sor_multi_company.md's "What does NOT need company_id" guidance.
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
