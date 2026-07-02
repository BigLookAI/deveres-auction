from odoo import fields, models


class SorAgreementLine(models.Model):
    _name = 'sor.agreement.line'
    _description = 'SOR Agreement Line'
    _order = 'agreement_id, id'

    agreement_id = fields.Many2one(
        comodel_name='sor.agreement',
        string='Agreement',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Product',
        required=True,
    )
