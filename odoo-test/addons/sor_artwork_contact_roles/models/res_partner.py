# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    """Bridge: extends res.partner with artwork relationship fields.

    Adds artwork_ids, artwork_count, and action_view_artworks to contacts.
    Also guards against deletion of creators who have linked artworks —
    the unlink() guard references is_creator from sor_contact_roles, which
    is valid here because this bridge depends on sor_contact_roles.
    """

    _inherit = 'res.partner'

    artwork_ids = fields.One2many(
        comodel_name='product.template',
        inverse_name='creator_id',
        string='Artworks',
        domain=[('product_type', '=', 'artwork')],
        help="All artworks created by this creator/artist",
    )

    artwork_count = fields.Integer(
        string='Artwork Count',
        compute='_compute_artwork_count',
        store=False,
        help="Number of artworks created by this creator",
    )

    @api.depends('artwork_ids')
    def _compute_artwork_count(self):
        """Compute the number of artworks for this creator."""
        for partner in self:
            partner.artwork_count = len(partner.artwork_ids)

    def action_view_artworks(self):
        """Action to view artworks created by this creator."""
        self.ensure_one()
        return {
            'name': _('Artworks by %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'list,form,kanban',
            'domain': [
                ('product_type', '=', 'artwork'),
                ('creator_id', '=', self.id),
                '|',
                ('company_id', '=', self.env.company.id),
                ('company_id', '=', False),
            ],
            'context': {
                'default_product_type': 'artwork',
                'default_creator_id': self.id,
                'search_default_active': 1,
            },
        }

    def unlink(self):
        """Prevent deletion of creators that have artworks."""
        for partner in self:
            if partner.is_creator and partner.artwork_ids:
                raise ValidationError(_(
                    "Cannot delete creator '%s' because they have %d artwork(s). "
                    "Please remove or reassign the artworks first.",
                ) % (partner.name, len(partner.artwork_ids)))
        return super().unlink()
