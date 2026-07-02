from odoo import api, fields, models

from .const import SUPPRESSIBLE_ELEMENTS


class SorAssetParadigmRule(models.Model):
    _name = 'sor.asset.paradigm.rule'
    _description = 'Asset Paradigm Suppression Rule'
    _order = 'paradigm, element_key'

    paradigm = fields.Char(
        string='Paradigm',
        required=True,
        index=True,
        help="The asset_paradigm value this rule applies to (e.g. 'unique_object').",
    )
    element_key = fields.Selection(
        selection=SUPPRESSIBLE_ELEMENTS,
        string='Element',
        required=True,
        help="The UI element this rule suppresses.",
    )
    active = fields.Boolean(
        string='Suppressed',
        default=True,
        help="When checked, this element is suppressed for the given paradigm. "
             "Uncheck to temporarily re-enable the element for debugging.",
    )
    description = fields.Char(
        string='Description',
        help="Human-readable note on what this element is and why it is suppressed.",
    )

    # --- Display metadata ---

    element_code = fields.Char(
        string='Element Key',
        compute='_compute_element_code',
        store=False,
        help="Technical key identifying this suppressible element (e.g. 'inventory_tab').",
    )
    manifestation_ids = fields.One2many(
        'sor.asset.paradigm.rule.manifestation',
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

    @api.depends('element_key')
    def _compute_element_code(self):
        for rec in self:
            rec.element_code = rec.element_key or ''

    @api.depends('manifestation_ids')
    def _compute_manifestation_count(self):
        for rec in self:
            rec.manifestation_count = len(rec.manifestation_ids)

    @api.depends('manifestation_ids.is_static')
    def _compute_has_static_manifestation(self):
        for rec in self:
            rec.has_static_manifestation = any(m.is_static for m in rec.manifestation_ids)

    _unique_paradigm_element = models.Constraint(
        'UNIQUE(paradigm, element_key)',
        'A suppression rule for this paradigm and element already exists.',
    )
