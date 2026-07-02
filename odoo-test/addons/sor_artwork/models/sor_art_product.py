# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SorArtProduct(models.Model):
    """SOR Product Model

    Extends product.template to add product-specific fields.
    Supports hierarchical product types:
    - Product Type 1: Artwork (1.1 Painting, 1.2 Sculpture, 1.3 Print, 1.4+)
    """
    _inherit = 'product.template'

    company_id = fields.Many2one(default=lambda self: self.env.company)

    # Level 1: Product Type (Primitive)
    # Note: Built-in Odoo 'type' field (Goods/Service/Combo) is for sales/inventory purposes
    # This field is for SOR product categorization (Artwork, etc.)
    product_type = fields.Selection(
        string='Type',
        selection=[('artwork', 'Artwork')],
        help="SOR product type. Extended by vertical modules via selection_add.",
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'product_type' in fields_list:
            ctx_type = self.env.context.get('default_product_type')
            if not ctx_type or ctx_type == 'artwork':
                defaults['product_type'] = 'artwork'
        return defaults

    # Level 2: Product Subtype (Type within each primitive)
    product_subtype = fields.Selection(
        string='Sub-type',
        selection='_get_product_subtype_selection',
        help="Product sub-type based on selected type",
    )

    @api.model
    def _get_product_subtype_selection(self):
        """Dynamic selection for product_subtype based on product_type"""
        # Return all possible options (filtering happens via widget in view)
        return [
            # Artwork subtypes
            ('painting', 'Painting'),
            ('sculpture', 'Sculpture'),
            ('print', 'Print'),
        ]

    def _get_subtype_options_for_type(self, product_type):
        """Helper method to get valid subtypes for a given product_type"""
        selections = {
            'artwork': ['painting', 'sculpture', 'print'],
        }
        return selections.get(product_type, [])

    # Computed field to provide whitelist for filterable_selection widget
    # Using Char field with comma-separated values that the widget can parse
    # The widget's .includes() method works on strings, checking for substring match
    product_subtype_whitelist = fields.Char(
        string='Product Subtype Whitelist',
        compute='_compute_product_subtype_whitelist',
        store=False,
        readonly=True,
        help="Technical field for filtering product_subtype options",
    )

    @api.depends('product_type')
    def _compute_product_subtype_whitelist(self):
        """Compute whitelist of valid subtypes for the selected product_type as comma-separated string"""
        for record in self:
            if record.product_type:
                valid_subtypes = record._get_subtype_options_for_type(record.product_type)
                # Format as comma-separated string for the widget's .includes() check
                # The widget checks: whitelist.includes(option[0])
                # Using comma-separated format: "painting,sculpture,print"
                record.product_subtype_whitelist = ','.join(valid_subtypes) if valid_subtypes else ''
            else:
                # Always set to empty string (not None/False) to avoid undefined errors in JavaScript
                # Empty string means no filtering (all options shown)
                record.product_subtype_whitelist = ''

    dimensions_width = fields.Float(
        string='Width',
        digits=(10, 2),
        help="Width dimension (required for artwork and furniture)",
    )

    dimensions_height = fields.Float(
        string='Height',
        digits=(10, 2),
        help="Height dimension (required for artwork and furniture)",
    )

    medium = fields.Char(
        string='Medium',
        size=255,
        help="Medium/Material (e.g., oil, acrylic, bronze, marble for artwork; wood, metal for furniture)",
    )

    creator_id = fields.Many2one(
        comodel_name='res.partner',
        string='Creator/Artist',
        help="Creator/Artist relationship. Only contacts with Creator type are shown when contact roles are installed.",
    )

    creation_year = fields.Integer(
        string='Creation Year',
        help="Year the artwork was created",
    )

    # Type-Specific Fields
    dimensions_depth = fields.Float(
        string='Depth',
        digits=(10, 2),
        help="Depth dimension (only for sculptures and 3D artworks). "
             "Required for sculptures.",
    )

    edition_info = fields.Text(
        string='Edition Information',
        help="Edition information (edition number, total editions, etc.). "
             "Only for sculptures and prints. Paintings do NOT have this field.",
    )

    # Optional Fields (Configurable)
    condition = fields.Text(
        string='Condition',
        help="Condition of the artwork",
    )

    provenance = fields.Text(
        string='Provenance',
        help="Provenance/history of ownership",
    )

    # Certificate Fields
    certificate_of_authenticity = fields.Boolean(
        string='Certificate of Authenticity',
        default=False,
        help="Whether certificate of authenticity exists",
    )

    certificate_attachment_ids = fields.One2many(
        comodel_name='ir.attachment',
        inverse_name='res_id',
        string='Certificate Attachments',
        domain=[('res_model', '=', 'product.template')],
        help="Certificate attachments",
    )

    # Image Management Fields
    work_image_ids = fields.One2many(
        comodel_name='sor.art.work.image',
        inverse_name='work_id',
        string='Artwork Images',
        help="Multiple images for this artwork (front, back, detail shots, etc.)",
    )

    # Validation Constraints
    @api.constrains('product_type', 'product_subtype')
    def _check_product_type_subtype(self):
        """Ensure product_subtype is valid for the selected product_type"""
        for record in self:
            if not record.product_type:
                continue
            if not record.product_subtype:
                continue

            valid_subtypes = record._get_subtype_options_for_type(record.product_type)

            if record.product_subtype not in valid_subtypes:
                raise ValidationError(_("Invalid product subtype '%s' for product type '%s'.") %
                                        (record.product_subtype, record.product_type))

    @api.constrains('dimensions_width', 'dimensions_height', 'product_type')
    def _check_dimensions_positive_and_required(self):
        """Ensure width and height are positive values and required for artwork"""
        for record in self:
            # Width and height are required for artwork
            if record.product_type == 'artwork':
                if not record.dimensions_width:
                    raise ValidationError(_("Width is required for %s products.") % record.product_type)
                if not record.dimensions_height:
                    raise ValidationError(_("Height is required for %s products.") % record.product_type)

            if record.dimensions_width and record.dimensions_width <= 0:
                raise ValidationError(_("Width must be a positive value."))
            if record.dimensions_height and record.dimensions_height <= 0:
                raise ValidationError(_("Height must be a positive value."))

    @api.constrains('dimensions_depth')
    def _check_depth_positive_and_required(self):
        """Ensure depth is positive and required for sculptures"""
        for record in self:
            if record.product_type == 'artwork' and record.product_subtype == 'sculpture':
                if not record.dimensions_depth:
                    raise ValidationError(_("Depth is required for sculptures."))
                if record.dimensions_depth <= 0:
                    raise ValidationError(_("Depth must be a positive value."))
            elif record.dimensions_depth and record.dimensions_depth <= 0:
                raise ValidationError(_("Depth must be a positive value if provided."))

    @api.constrains('creation_year')
    def _check_creation_year_range(self):
        """Validate creation year is in reasonable range"""
        for record in self:
            if record.creation_year:
                if record.creation_year < 1000 or record.creation_year > 2100:
                    raise ValidationError(_("Creation year must be between 1000 and 2100."))

    @api.constrains('creator_id', 'product_type')
    def _check_creator_required(self):
        """Validate that creator is required for artworks"""
        for record in self:
            if record.product_type == 'artwork' and not record.creator_id:
                raise ValidationError(_("Creator/Artist is required for artworks."))

    @api.onchange('product_type')
    def _onchange_product_type(self):
        """Auto-select first subtype when product_type changes and clear invalid subtype"""
        # Force computation of whitelist field to ensure it's available for the widget
        self._compute_product_subtype_whitelist()

        if self.product_type:
            # Get valid subtypes for the selected product_type
            valid_subtypes = self._get_subtype_options_for_type(self.product_type)

            # If current subtype is not valid for the new product_type, clear it
            if self.product_subtype and self.product_subtype not in valid_subtypes:
                self.product_subtype = False

            # Auto-select the first available subtype if none selected
            if not self.product_subtype and valid_subtypes:
                self.product_subtype = valid_subtypes[0]
            elif not valid_subtypes:
                # Clear if no subtypes available for this product_type
                self.product_subtype = False
        else:
            # Ensure whitelist is empty when no product_type
            self.product_subtype_whitelist = ''

    @api.onchange('product_subtype')
    def _onchange_product_subtype(self):
        """Handle field visibility and requirements when product_subtype changes"""
        if self.product_type == 'artwork':
            if self.product_subtype == 'painting':
                # Paintings don't have edition_info
                if self.edition_info:
                    self.edition_info = False
            # For sculptures, depth is required (handled by constraint)
            # For prints, depth is optional
