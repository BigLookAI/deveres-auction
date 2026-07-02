from odoo import fields, models


class SorAssetParadigmRuleManifestation(models.Model):
    _name = 'sor.asset.paradigm.rule.manifestation'
    _description = 'Asset Paradigm Rule UI Manifestation'
    _order = 'rule_id, id'

    rule_id = fields.Many2one(
        'sor.asset.paradigm.rule',
        string='Rule',
        required=True,
        ondelete='cascade',
        index=True,
    )
    element_name = fields.Char(
        string='Element Name',
        required=True,
        help="Human-readable name of this specific UI element "
             "(e.g. 'Forecasted Qty Smart Button', 'Sales Price Column').",
    )
    element_key = fields.Char(
        string='Element Key',
        required=True,
        help="Odoo's own technical identifier for this element — the field name, "
             "page name, or button name targeted by the suppression XPath "
             "(e.g. 'qty_available', 'inventory', 'list_price').",
    )
    ui_element_type = fields.Char(
        string='Element Type',
        required=True,
        help="Type of UI element, per Odoo nomenclature "
             "(e.g. 'Form Tab', 'Smart Button', 'Field', 'List Column').",
    )
    ui_location = fields.Char(
        string='UI Location',
        required=True,
        help="Odoo UI path where this suppression is applied "
             "(e.g. 'Product Template Form > General Information Tab').",
    )
    is_static = fields.Boolean(
        string='Statically Suppressed',
        default=False,
        help="When True, this suppression is applied at the module level and is not "
             "affected by the parent rule's Suppressed toggle at runtime.",
    )
    static_marker = fields.Char(
        string=' ',
        compute='_compute_static_marker',
        store=False,
    )

    def _compute_static_marker(self):
        for rec in self:
            rec.static_marker = '*' if rec.is_static else ''
