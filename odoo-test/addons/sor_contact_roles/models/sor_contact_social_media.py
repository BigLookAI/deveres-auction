# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SorContactSocialMedia(models.Model):
    _name = 'sor.contact.social.media'
    _description = 'SOR Contact Social Media'
    _order = 'partner_id, platform, id'

    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        required=True,
        ondelete='cascade',
        index=True,
        help="Contact this social media profile belongs to.",
    )
    platform = fields.Selection(
        [
            ('instagram', 'Instagram'),
            ('facebook', 'Facebook'),
            ('twitter', 'Twitter/X'),
            ('linkedin', 'LinkedIn'),
            ('website', 'Website'),
            ('other', 'Other'),
        ],
        string='Platform',
        required=True,
        help="Social media platform or website.",
    )
    handle = fields.Char(
        string='Handle/Username',
        required=True,
        help="Username, handle, or URL for this social media profile.",
    )
    url = fields.Char(
        string='Full URL',
        compute='_compute_url',
        store=True,
        help="Full URL to the social media profile.",
    )
    active = fields.Boolean(
        default=True,
        help="Uncheck to archive this social media profile.",
    )

    @api.depends('platform', 'handle')
    def _compute_url(self):
        """Compute full URL based on platform and handle."""
        for record in self:
            if not record.platform or not record.handle:
                record.url = False
                continue

            handle = record.handle.strip()

            # If handle already looks like a URL, use it directly
            if handle.startswith(('http://', 'https://')):
                record.url = handle
                continue

            # Build URL based on platform
            url_map = {
                'instagram': f'https://www.instagram.com/{handle.lstrip("@")}',
                'facebook': f'https://www.facebook.com/{handle.lstrip("@")}',
                'twitter': f'https://twitter.com/{handle.lstrip("@")}',
                'linkedin': f'https://www.linkedin.com/in/{handle.lstrip("/")}',
                'website': handle if handle.startswith(('http://', 'https://')) else f'https://{handle}',
                'other': handle if handle.startswith(('http://', 'https://')) else f'https://{handle}',
            }

            record.url = url_map.get(record.platform, handle)

    @api.constrains('partner_id', 'platform', 'handle')
    def _check_unique_platform_handle(self):
        """Ensure unique platform+handle combination per partner."""
        for record in self:
            if record.partner_id and record.platform and record.handle:
                duplicate = self.search([
                    ('partner_id', '=', record.partner_id.id),
                    ('platform', '=', record.platform),
                    ('handle', '=', record.handle),
                    ('id', '!=', record.id),
                    ('active', '=', True),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        _("Social media profile with platform '%(platform)s' and handle '%(handle)s' "
                          "already exists for this contact.") % {
                            'platform': record.platform,
                            'handle': record.handle,
                        },
                    )
