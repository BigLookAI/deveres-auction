# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SorRoom(models.Model):
    _inherit = 'stock.location'

    viewing_location_id = fields.Many2one(
        'stock.warehouse',
        related='warehouse_id',
        string='Viewing Location',
        store=False,
        help="The Viewing Location (warehouse) this Room belongs to.",
    )

    @api.constrains('location_id', 'usage')
    def _check_room_parent_is_viewing_location(self):
        """A Room (internal location under a warehouse) must be a direct child
        of a Viewing Location's top-level location, not of another Room.

        Uses the parent's warehouse_id (already computed, since the parent is
        an existing record) rather than the new record's own warehouse_id
        (which may not yet be computed when the constraint fires).
        """
        for record in self:
            if record.usage != 'internal' or not record.location_id:
                continue
            parent = record.location_id
            # parent.warehouse_id set + parent is NOT a warehouse view location
            # → parent is another Room or sub-location, not a Viewing Location
            if parent.warehouse_id and not parent.warehouse_view_ids:
                raise ValidationError(
                    _("A Room's parent must be a Viewing Location, not another Room. "
                      "Please select a Viewing Location as the parent."),
                )
