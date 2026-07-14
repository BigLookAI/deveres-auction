from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    effective_business_model = fields.Char(
        string='Effective Business Model',
        compute='_compute_effective_business_model',
        store=False,
    )

    def _compute_effective_business_model(self):
        model = self.env.company.business_model
        for rec in self:
            rec.effective_business_model = model

    def is_field_suppressed(self, field_key):
        if not self.effective_business_model:
            return False
        return bool(
            self.env['sor.business.model.rule'].search_count([
                ('business_model', '=', self.effective_business_model),
                ('field_key', '=', field_key),
                ('active', '=', True),
            ]),
        )
