# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class SorArtWorkImage(models.Model):
    """SOR Artwork Image Model

    Stores multiple images per artwork (front, back, detail shots, etc.)
    with support for upload, display, and reordering.
    """
    _name = 'sor.art.work.image'
    _description = 'Artwork Image'
    _order = 'sequence, id'

    work_id = fields.Many2one(
        comodel_name='product.template',
        string='Artwork',
        required=True,
        ondelete='cascade',
        help="The artwork this image belongs to",
    )

    name = fields.Char(
        string='Image Description',
        help="Description or label for this image (e.g., 'Front view', 'Detail shot', etc.)",
    )

    image = fields.Image(
        string='Image',
        max_width=1920,
        max_height=1920,
        help="Image file for this artwork. Stored at up to 1920×1920px.",
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Order in which images are displayed (lower numbers first)",
    )
