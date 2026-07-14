from odoo import api, fields, models

from .const import SUPPRESSIBLE_FIELDS


class SorBusinessModelRule(models.Model):
    _name = 'sor.business.model.rule'
    _description = 'Business Model Suppression Rule'
    _order = 'business_model, field_key'

    business_model = fields.Char(
        string='Business Model',
        required=True,
        index=True,
    )
    field_key = fields.Selection(
        selection=SUPPRESSIBLE_FIELDS,
        string='Element',
        required=True,
    )
    active = fields.Boolean(
        string='Suppressed',
        default=True,
        help="When checked, this field is suppressed for the given business model.",
    )
    description = fields.Char(string='Description')

    # --- Display metadata ---

    field_code = fields.Char(
        string='Element Key',
        compute='_compute_field_code',
        store=False,
        help="Technical key identifying this suppressible element (e.g. 'sales_tab').",
    )
    manifestation_ids = fields.One2many(
        'sor.business.model.rule.manifestation',
        'rule_id',
        string='UI Manifestations',
    )
    manifestation_count = fields.Integer(
        string='Instances',
        compute='_compute_manifestation_count',
        store=False,
    )
    has_static_manifestation = fields.Boolean(
        compute='_compute_has_static_manifestation',
        store=False,
    )

    @api.depends('field_key')
    def _compute_field_code(self):
        for rec in self:
            rec.field_code = rec.field_key or ''

    @api.depends('manifestation_ids')
    def _compute_manifestation_count(self):
        for rec in self:
            rec.manifestation_count = len(rec.manifestation_ids)

    @api.depends('manifestation_ids.is_static')
    def _compute_has_static_manifestation(self):
        for rec in self:
            rec.has_static_manifestation = any(m.is_static for m in rec.manifestation_ids)
