# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

ACTIVITY_EARNED_CODES = frozenset({'bidder', 'buyer', 'consignor', 'donor', 'lender'})


class ResPartner(models.Model):
    _inherit = 'res.partner'

    contact_types = fields.Many2many(
        comodel_name='sor.contact.type',
        relation='sor_contact_type_res_partner_rel',
        column1='partner_id',
        column2='contact_type_id',
        string='Contact Types',
        domain=[('parent_type_id', '=', False)],
        help="Assign one or more contact types (e.g. Creator + Contact). "
             "Sub-types will appear in a separate field below when parent types are selected.",
    )

    contact_subtypes = fields.Many2many(
        comodel_name='sor.contact.type',
        relation='sor_contact_subtype_res_partner_rel',
        column1='partner_id',
        column2='contact_type_id',
        string='Sub-Types',
        help="Select specific sub-types for the selected parent contact types. "
             "This field appears when Creator or Contact is selected.",
    )

    show_subtypes = fields.Boolean(
        compute='_compute_show_subtypes',
        string='Show Sub-Types',
        help="Technical field to control visibility of sub-types field.",
    )

    activity_earned_subtype_ids = fields.Many2many(
        comodel_name='sor.contact.type',
        compute='_compute_activity_earned_subtypes',
        store=False,
        string='System-Assigned Roles',
    )

    staff_subtype_ids = fields.Many2many(
        comodel_name='sor.contact.type',
        compute='_compute_staff_subtype_ids',
        inverse='_inverse_staff_subtype_ids',
        store=False,
        string='Staff-Assignable Sub-Types',
    )

    creator_subtypes = fields.Many2many(
        comodel_name='sor.contact.type',
        compute='_compute_creator_subtypes',
        store=False,
        string='Creator Sub-Types',
    )

    contact_role_subtypes = fields.Many2many(
        comodel_name='sor.contact.type',
        compute='_compute_contact_role_subtypes',
        store=False,
        string='Contact Sub-Types',
    )

    @api.depends('contact_subtypes')
    def _compute_activity_earned_subtypes(self):
        for partner in self:
            partner.activity_earned_subtype_ids = partner.contact_subtypes.filtered(
                lambda t: t.code in ACTIVITY_EARNED_CODES,
            )

    @api.depends('contact_subtypes')
    def _compute_staff_subtype_ids(self):
        for partner in self:
            partner.staff_subtype_ids = partner.contact_subtypes.filtered(
                lambda t: t.code not in ACTIVITY_EARNED_CODES,
            )

    def _inverse_staff_subtype_ids(self):
        for partner in self:
            earned = partner.contact_subtypes.filtered(
                lambda t: t.code in ACTIVITY_EARNED_CODES,
            )
            partner.contact_subtypes = partner.staff_subtype_ids | earned

    @api.depends('contact_subtypes', 'contact_subtypes.parent_type_id')
    def _compute_creator_subtypes(self):
        for partner in self:
            partner.creator_subtypes = partner.contact_subtypes.filtered(
                lambda t: t.parent_type_id and t.parent_type_id.code == 'creator',
            )

    @api.depends('contact_subtypes', 'contact_subtypes.parent_type_id')
    def _compute_contact_role_subtypes(self):
        for partner in self:
            partner.contact_role_subtypes = partner.contact_subtypes.filtered(
                lambda t: t.parent_type_id and t.parent_type_id.code == 'contact',
            )

    @api.depends('contact_types', 'contact_types.code')
    def _compute_show_subtypes(self):
        for partner in self:
            # Show sub-types field if Creator or Contact is selected
            codes = set(partner.contact_types.mapped('code'))
            partner.show_subtypes = 'creator' in codes or 'contact' in codes

    @api.onchange('contact_types')
    def _onchange_contact_types(self):
        """Auto-select default sub-types when parent types are selected."""
        if not self.contact_types:
            # Clear only staff-assignable sub-types; preserve earned ones.
            staff = self.contact_subtypes.filtered(
                lambda t: t.code not in ACTIVITY_EARNED_CODES,
            )
            if staff:
                self.contact_subtypes -= staff
            return

        # Auto-assign Artist when Creator is selected
        default_subtypes = self.env['sor.contact.type']
        for parent_type in self.contact_types:
            if parent_type.code == 'creator':
                artist = self.env['sor.contact.type'].search([
                    ('code', '=', 'artist'),
                    ('parent_type_id.code', '=', 'creator'),
                ], limit=1)
                if artist and artist not in self.contact_subtypes:
                    default_subtypes |= artist

        if default_subtypes:
            self.contact_subtypes |= default_subtypes

        # Remove invalid staff sub-types (earned sub-types are never removed by this onchange)
        if self.contact_subtypes:
            valid_parent_ids = self.contact_types.ids
            invalid_subtypes = self.contact_subtypes.filtered(
                lambda st: st.code not in ACTIVITY_EARNED_CODES
                          and st.parent_type_id
                          and st.parent_type_id.id not in valid_parent_ids,
            )
            if invalid_subtypes:
                self.contact_subtypes -= invalid_subtypes

    # ==========================================
    # Computed flags
    # ==========================================

    is_creator = fields.Boolean(compute='_compute_contact_type_flags', store=True, readonly=True)
    is_contact = fields.Boolean(compute='_compute_contact_type_flags', store=True, readonly=True)
    is_bidder = fields.Boolean(compute='_compute_contact_type_flags', store=True, readonly=True)
    is_donor = fields.Boolean(compute='_compute_contact_type_flags', store=True, readonly=True)
    is_consignor = fields.Boolean(compute='_compute_contact_type_flags', store=True, readonly=True)

    # Helper alias for Creator sub-type
    is_artist = fields.Boolean(compute='_compute_contact_type_flags', store=True, readonly=True)

    @api.depends('contact_types', 'contact_types.code', 'contact_types.type_category',
                 'contact_subtypes', 'contact_subtypes.code', 'contact_subtypes.parent_type_id')
    def _compute_contact_type_flags(self):
        for partner in self:
            # Combine parent types and sub-types for computation
            all_assigned_types = partner.contact_types | partner.contact_subtypes

            if not all_assigned_types:
                # No contact types assigned — set all flags to False
                partner.is_creator = False
                partner.is_contact = False
                partner.is_bidder = False
                partner.is_donor = False
                partner.is_consignor = False
                partner.is_artist = False
                continue

            # Get codes from both parent types and sub-types
            codes = set(all_assigned_types.mapped('code'))

            # Get all parent types (from direct assignment or from sub-types)
            parent_types = partner.contact_types
            for subtype in partner.contact_subtypes:
                if subtype.parent_type_id:
                    parent_types |= subtype.parent_type_id

            # Combine for category checking
            all_types = parent_types | partner.contact_subtypes

            # is_creator: True if contact has Creator type OR any Creator sub-type
            creator_types = all_types.filtered(lambda ct: ct.type_category == 'creator')
            partner.is_creator = bool(creator_types)

            # is_artist: True if contact has Artist sub-type OR Creator type (backward compat)
            partner.is_artist = bool(codes & {'artist'}) or bool(codes & {'creator'})

            # is_contact: True if contact has Contact parent type OR any Contact sub-type
            contact_types = all_types.filtered(lambda ct: ct.type_category == 'contact')
            partner.is_contact = bool(contact_types)

            # Activity-earned sub-type flags
            partner.is_bidder = 'bidder' in codes
            partner.is_donor = 'donor' in codes
            partner.is_consignor = 'consignor' in codes

    # ==========================================
    # Contact Type-Specific helper fields
    # ==========================================

    has_creator_type = fields.Boolean(
        compute='_compute_has_contact_type',
        store=True,
        string='Has Creator Type',
        help="Technical field: True if contact has Creator type or any Creator sub-type.",
    )
    has_contact_type = fields.Boolean(
        compute='_compute_has_contact_type',
        store=True,
        string='Has Contact Type',
        help="Technical field: True if contact has Contact type or any Contact sub-type.",
    )

    @api.depends('contact_types', 'contact_types.type_category',
                 'contact_subtypes', 'contact_subtypes.type_category', 'contact_subtypes.parent_type_id')
    def _compute_has_contact_type(self):
        """Compute helper fields for field visibility in views."""
        for partner in self:
            # Combine parent types and sub-types
            all_types = partner.contact_types | partner.contact_subtypes

            # Check for Creator type or Creator sub-types
            creator_types = all_types.filtered(lambda ct: ct.type_category == 'creator')
            partner.has_creator_type = bool(creator_types)

            # Check for Contact type or Contact sub-types
            contact_types = all_types.filtered(lambda ct: ct.type_category == 'contact')
            partner.has_contact_type = bool(contact_types)

    # ==========================================
    # Auto-parent-assignment — ORM overrides (C5 fix)
    # ==========================================

    @api.model
    def default_get(self, fields_list):
        """Pre-assign parent contact type when navigating from a type-specific window action.

        The window action sets ``default_contact_type_code`` in the context. This override
        reads that key and adds the corresponding parent type to the ``contact_types`` field
        defaults so that gallery staff do not need to select a type manually.
        """
        defaults = super().default_get(fields_list)
        type_code = self.env.context.get('default_contact_type_code')
        if type_code and 'contact_types' in fields_list:
            contact_type = self.env['sor.contact.type'].search(
                [('code', '=', type_code), ('parent_type_id', '=', False)],
                limit=1,
            )
            if contact_type:
                defaults['contact_types'] = [(4, contact_type.id)]
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-assign company_id for regular contacts and ensure parent types for sub-types.

        Company-backing partners (is_company=True) are globally shared and must not be
        scoped to a specific company — doing so breaks Odoo's _check_company() validation
        when creating warehouses and other company-scoped records.
        """
        for vals in vals_list:
            if not vals.get('is_company') and not vals.get('company_id'):
                vals['company_id'] = self.env.company.id
        records = super().create(vals_list)
        records._ensure_parent_type_for_subtypes()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'contact_subtypes' in vals:
            self._ensure_parent_type_for_subtypes()
        return result

    def _ensure_parent_type_for_subtypes(self):
        """Ensure that when a sub-type is assigned, its parent type is also assigned.

        This replaces the former @api.constrains method that incorrectly performed
        ORM writes inside a constraint validator (Bug C5).
        """
        for partner in self:
            for subtype in partner.contact_subtypes:
                if subtype.parent_type_id and subtype.parent_type_id not in partner.contact_types:
                    partner.contact_types = [(4, subtype.parent_type_id.id)]

    # ==========================================
    # Creator Fields (visible when Creator type or any Creator sub-type is assigned)
    # ==========================================

    biography = fields.Text(
        string='Biography',
        help="Biography of the creator/artist.",
    )
    birth_date = fields.Date(
        string='Birth Date',
        help="Birth date of the creator/artist.",
    )
    nationality = fields.Many2one(
        'res.country',
        string='Nationality',
        help="Nationality of the creator/artist.",
    )
    creator_website = fields.Char(
        string='Website',
        size=512,
        help="Website URL of the creator/artist.",
    )
    social_media_ids = fields.One2many(
        'sor.contact.social.media',
        'partner_id',
        string='Social Media',
        help="Social media profiles for this creator/artist.",
    )

    # Contact Fields (visible when Contact type or any Contact sub-type is assigned)
    collection_focus = fields.Text(
        string='Collection Focus',
        help="Description of collection focus and interests.",
    )
    preferred_artist_ids = fields.Many2many(
        'res.partner',
        'sor_contact_preferred_artist_rel',
        'partner_id',
        'preferred_artist_id',
        string='Preferred Artists',
        domain=[('is_creator', '=', True)],
        help="Preferred artists/creators in the collection.",
    )

    def _get_creator_type_ids(self):
        """Get all Creator type IDs (parent type and all sub-types).

        Returns: recordset of sor.contact.type records
        """
        ContactType = self.env['sor.contact.type']
        creator_parent = ContactType.search([('code', '=', 'creator'), ('parent_type_id', '=', False)], limit=1)
        if not creator_parent:
            return ContactType
        # Get parent and all sub-types
        return creator_parent | creator_parent.child_ids

    def _get_contact_type_ids(self):
        """Get all Contact type IDs (parent type and all sub-types).

        Returns: recordset of sor.contact.type records
        """
        ContactType = self.env['sor.contact.type']
        contact_parent = ContactType.search([('code', '=', 'contact'), ('parent_type_id', '=', False)], limit=1)
        if not contact_parent:
            return ContactType
        # Get parent and all sub-types
        return contact_parent | contact_parent.child_ids
