# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SorArtProductContactRoles(models.Model):
    """Bridge: extends product.template with sor_contact_roles coupling.

    Adds the creator_id domain restriction and validation constraint that
    reference sor_contact_roles fields (is_creator, is_artist). These
    references are valid here because this bridge depends on sor_contact_roles.
    """

    _inherit = 'product.template'

    creator_id = fields.Many2one(domain="[('is_creator', '=', True)]")

    @api.constrains('creator_id')
    def _check_creator_is_valid(self):
        """Validate that selected creator has creator/artist contact type."""
        for record in self:
            if record.creator_id and record.product_type == 'artwork':
                if not record.creator_id.is_creator and not record.creator_id.is_artist:
                    raise ValidationError(_(
                        "Selected creator '%s' does not have Creator/Artist contact type. "
                        "Please select a contact with Creator or Artist type.",
                    ) % record.creator_id.name)
