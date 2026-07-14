# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SorContactType(models.Model):
    _name = 'sor.contact.type'
    _description = 'SOR Contact Type'
    _order = 'sequence, name, id'
    _check_company_auto = True

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        index=True,
        help="Technical identifier used for computed helper fields and domains "
             "(e.g. 'creator', 'contact', 'bidder').",
    )
    description = fields.Text(translate=True)

    # Parent-child hierarchy support
    parent_type_id = fields.Many2one(
        'sor.contact.type',
        string='Parent Type',
        ondelete='restrict',
        help="Parent contact type for sub-types (e.g., Artist is a sub-type of Creator).",
    )
    type_category = fields.Selection(
        [
            ('creator', 'Creator'),
            ('contact', 'Contact'),
            ('other', 'Other'),
        ],
        string='Type Category',
        default='other',
        help="Category to group contact types and their sub-types.",
    )
    color = fields.Integer(
        string='Color Index',
        default=0,
        help="Color for Kanban view grouping. 0=No color, 1=Red, 2=Orange, 3=Yellow, 4=Light Blue, 5=Dark Purple, 6=Salmon Pink, 7=Medium Blue, 8=Dark Blue, 9=Fuchsia, 10=Green, 11=Purple",
    )

    # Optional: allow company-specific contact types later; seeded types are global (company_id = False).
    company_id = fields.Many2one('res.company', string='Company', index=True)

    # Computed field for child types
    child_ids = fields.One2many(
        'sor.contact.type',
        'parent_type_id',
        string='Sub-Types',
        help="Sub-types of this contact type.",
    )

    _code_uniq = models.Constraint(
        'unique(code)',
        'Contact type code must be unique.',
    )

    @api.constrains('parent_type_id')
    def _check_parent_type(self):
        """Prevent circular references in parent-child hierarchy."""
        for record in self:
            if record.parent_type_id:
                # Check for direct self-reference
                if record.parent_type_id.id == record.id:
                    raise ValidationError(
                        _("A contact type cannot be its own parent."),
                    )

                # Check for circular references in the chain
                parent = record.parent_type_id
                visited = {record.id}
                while parent:
                    if parent.id in visited:
                        raise ValidationError(
                            _("Circular reference detected in contact type hierarchy. "
                              "A contact type cannot be its own parent or ancestor."),
                        )
                    visited.add(parent.id)
                    parent = parent.parent_type_id
