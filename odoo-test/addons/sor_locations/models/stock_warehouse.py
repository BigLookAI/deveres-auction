# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, models
from odoo.exceptions import ValidationError


class SorViewingLocation(models.Model):
    _inherit = 'stock.warehouse'

    @api.constrains('partner_id')
    def _check_partner_required(self):
        """A Viewing Location must have an address (partner_id)."""
        for record in self:
            if not record.partner_id:
                raise ValidationError(
                    _("A Viewing Location requires an address. "
                      "Please set an address before saving."),
                )

    @api.onchange('company_id')
    def _onchange_company_id_check_address(self):
        """Warn if the selected company has no address configured."""
        if self.company_id and not self.company_id.partner_id:
            return {
                'warning': {
                    'title': _('No Company Address'),
                    'message': _(
                        "Company '%(name)s' has no address configured. "
                        "Go to Settings → Companies to add one.",
                        name=self.company_id.name,
                    ),
                },
            }
        return None
