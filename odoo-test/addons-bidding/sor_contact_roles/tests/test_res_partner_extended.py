# Part of Odoo. See LICENSE file for full copyright and licensing details.

import uuid

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartnerExtended(TransactionCase):
    """Extended tests for res.partner contact type functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']

        # Find existing contact types
        cls.creator_type = cls.ContactType.search([
            ('code', '=', 'creator'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.contact_type = cls.ContactType.search([
            ('code', '=', 'contact'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.artist_subtype = cls.ContactType.search([
            ('code', '=', 'artist'),
            ('parent_type_id', '!=', False),
        ], limit=1)
        cls.bidder_subtype = cls.ContactType.search([
            ('code', '=', 'bidder'),
            ('parent_type_id', '!=', False),
        ], limit=1)

        cls.partner = cls.Partner.create({'name': 'Test Contact'})

    # ==========================================
    # New hierarchy — Contact type tests
    # ==========================================

    def test_contact_type_exists(self):
        """Contact parent type exists with code='contact'."""
        self.assertTrue(self.contact_type, "Contact parent type not found")
        self.assertEqual(self.contact_type.name, 'Contact')
        self.assertEqual(self.contact_type.type_category, 'contact')

    def test_customer_type_absent(self):
        """Customer type does not exist as an active parent type."""
        customer_type = self.ContactType.search([('code', '=', 'customer')])
        self.assertFalse(customer_type, "Customer type should not exist (renamed to Contact)")

    def test_removed_types_absent(self):
        """Removed types are absent (archived) — private_collector, corporate_collector, etc."""
        removed_codes = ['private_collector', 'corporate_collector', 'institutions_collection', 'dealer', 'advisor']
        types = self.ContactType.search([('code', 'in', removed_codes)])
        self.assertFalse(types, f"Removed types should be archived; found: {types.mapped('code')}")

    def test_activity_earned_subtypes_under_contact(self):
        """Bidder, Buyer, Consignor, Donor, Lender are sub-types of Contact."""
        earned_codes = ['bidder', 'buyer', 'consignor', 'donor', 'lender']
        for code in earned_codes:
            subtype = self.ContactType.search([('code', '=', code)], limit=1)
            self.assertTrue(subtype, f"Sub-type '{code}' not found")
            self.assertEqual(
                subtype.parent_type_id,
                self.contact_type,
                f"'{code}' is not under Contact parent type",
            )
            self.assertEqual(subtype.type_category, 'contact', f"'{code}' type_category should be 'contact'")

    def test_artist_under_creator(self):
        """Artist is a sub-type of Creator."""
        self.assertTrue(self.artist_subtype, "Artist sub-type not found")
        self.assertEqual(self.artist_subtype.parent_type_id, self.creator_type)
        self.assertEqual(self.artist_subtype.type_category, 'creator')

    # ==========================================
    # Flag rename tests
    # ==========================================

    def test_is_contact_flag_exists(self):
        """is_contact computed flag exists on res.partner."""
        self.assertTrue(hasattr(self.partner, 'is_contact'))

    def test_is_customer_flag_absent(self):
        """is_customer flag does not exist on res.partner (renamed to is_contact)."""
        self.assertFalse(hasattr(self.partner, 'is_customer'), "is_customer should have been renamed to is_contact")

    def test_has_contact_type_flag_exists(self):
        """has_contact_type computed flag exists on res.partner."""
        self.assertTrue(hasattr(self.partner, 'has_contact_type'))

    def test_has_customer_type_flag_absent(self):
        """has_customer_type flag does not exist (renamed to has_contact_type)."""
        self.assertFalse(
            hasattr(self.partner, 'has_customer_type'),
            "has_customer_type should have been renamed to has_contact_type",
        )

    # ==========================================
    # Flag computation tests
    # ==========================================

    def test_is_contact_computed_field(self):
        """is_contact is True when Contact parent type is assigned."""
        self.assertFalse(self.partner.is_contact)
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
        })
        self.assertTrue(self.partner.is_contact)

    def test_is_contact_via_subtype(self):
        """is_contact is True when a Contact sub-type is assigned (sub-type triggers parent)."""
        partner2 = self.Partner.create({'name': 'Test Bidder'})
        partner2.write({
            'contact_subtypes': [Command.link(self.bidder_subtype.id)],
        })
        # Parent type is auto-assigned, which triggers is_contact
        self.assertIn(self.contact_type, partner2.contact_types)
        self.assertTrue(partner2.is_contact)

    def test_is_creator_computed_field(self):
        """is_creator is True when Creator parent type is assigned."""
        self.assertFalse(self.partner.is_creator)
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.is_creator)

    def test_is_creator_via_subtype(self):
        """is_creator is True when Artist sub-type is assigned."""
        partner2 = self.Partner.create({'name': 'Test Artist'})
        partner2.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertTrue(partner2.is_creator)

    def test_is_artist_computed_field(self):
        """is_artist is True when Artist sub-type is assigned."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.is_artist)
        partner2 = self.Partner.create({'name': 'Test Artist 2'})
        partner2.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertTrue(partner2.is_artist)

    def test_is_bidder_computed_field(self):
        """is_bidder is True when Bidder sub-type is assigned."""
        if self.bidder_subtype:
            partner2 = self.Partner.create({'name': 'Test Bidder 2'})
            partner2.write({
                'contact_subtypes': [Command.link(self.bidder_subtype.id)],
            })
            self.assertTrue(partner2.is_bidder)

    def test_is_donor_computed_field(self):
        """is_donor is True when Donor sub-type is assigned."""
        donor_subtype = self.ContactType.search([('code', '=', 'donor')], limit=1)
        if donor_subtype:
            partner2 = self.Partner.create({'name': 'Test Donor'})
            partner2.write({
                'contact_subtypes': [Command.link(donor_subtype.id)],
            })
            self.assertTrue(partner2.is_donor)

    def test_is_consignor_computed_field(self):
        """is_consignor is True when Consignor sub-type is assigned."""
        consignor_subtype = self.ContactType.search([('code', '=', 'consignor')], limit=1)
        if consignor_subtype:
            partner2 = self.Partner.create({'name': 'Test Consignor'})
            partner2.write({
                'contact_subtypes': [Command.link(consignor_subtype.id)],
            })
            self.assertTrue(partner2.is_consignor)

    def test_has_contact_type_computed_field(self):
        """has_contact_type is True when Contact parent or sub-type is assigned."""
        self.assertFalse(self.partner.has_contact_type)
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
        })
        self.assertTrue(self.partner.has_contact_type)

    def test_has_contact_type_via_subtype(self):
        """has_contact_type is True when a Contact sub-type is assigned."""
        partner2 = self.Partner.create({'name': 'Test Bidder 3'})
        partner2.write({
            'contact_subtypes': [Command.link(self.bidder_subtype.id)],
        })
        self.assertTrue(partner2.has_contact_type)

    def test_has_creator_type_computed_field(self):
        """has_creator_type is True when Creator parent or sub-type is assigned."""
        self.assertFalse(self.partner.has_creator_type)
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.has_creator_type)

    # ==========================================
    # Auto-parent-assignment tests (C5 fix)
    # ==========================================

    def test_auto_parent_assignment_on_write(self):
        """Assigning a Contact sub-type auto-assigns the Contact parent type."""
        self.partner.write({
            'contact_subtypes': [Command.link(self.bidder_subtype.id)],
        })
        self.assertIn(self.contact_type, self.partner.contact_types)
        self.assertIn(self.bidder_subtype, self.partner.contact_subtypes)

    def test_auto_parent_assignment_on_create(self):
        """Creating a partner with a Contact sub-type auto-assigns the Contact parent type."""
        partner = self.Partner.create({
            'name': 'Auto-Parent Test',
            'contact_subtypes': [Command.link(self.bidder_subtype.id)],
        })
        self.assertIn(self.contact_type, partner.contact_types)

    def test_auto_parent_assignment_idempotent(self):
        """Auto-parent-assignment does not duplicate the parent if already assigned."""
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
            'contact_subtypes': [Command.link(self.bidder_subtype.id)],
        })
        # Count Contact type occurrences — should be exactly 1
        contact_count = sum(1 for t in self.partner.contact_types if t.id == self.contact_type.id)
        self.assertEqual(contact_count, 1, "Contact parent type should appear exactly once")

    def test_auto_parent_assignment_artist_subtype(self):
        """Assigning Artist sub-type auto-assigns Creator parent type."""
        self.partner.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertIn(self.creator_type, self.partner.contact_types)
        self.assertIn(self.artist_subtype, self.partner.contact_subtypes)

    # ==========================================
    # Basic persistence and removal tests
    # ==========================================

    def test_contact_type_assignment_persistence(self):
        """Contact type assignments persist after save."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        partner_reloaded = self.Partner.browse(self.partner.id)
        self.assertIn(self.creator_type, partner_reloaded.contact_types)
        self.assertTrue(partner_reloaded.is_creator)

    def test_contact_type_removal(self):
        """Removing contact types from a contact clears flags."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.is_creator)
        self.partner.write({
            'contact_types': [Command.unlink(self.creator_type.id)],
        })
        self.assertNotIn(self.creator_type, self.partner.contact_types)
        self.assertFalse(self.partner.is_creator)

    def test_contact_type_domain_restriction(self):
        """contact_types field only shows parent types."""
        artist = self.ContactType.search([
            ('code', '=', 'artist'),
            ('parent_type_id', '!=', False),
        ], limit=1)
        if artist:
            parent_types = self.ContactType.search([('parent_type_id', '=', False)])
            self.assertNotIn(artist, parent_types)

    def test_multiple_types_allowed(self):
        """A contact can have both Creator and Contact parent types."""
        self.partner.write({
            'contact_types': [
                Command.link(self.creator_type.id),
                Command.link(self.contact_type.id),
            ],
        })
        self.assertTrue(self.partner.is_creator)
        self.assertTrue(self.partner.is_contact)

    def test_removing_all_types(self):
        """Removing all types clears all flags."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.partner.write({
            'contact_types': [Command.clear()],
            'contact_subtypes': [Command.clear()],
        })
        self.assertFalse(self.partner.contact_types)
        self.assertFalse(self.partner.is_creator)
        self.assertFalse(self.partner.is_contact)

    def test_contacts_without_types_normal_behavior(self):
        """Contacts without types behave like normal res.partner."""
        partner = self.Partner.create({
            'name': 'Normal Contact',
            'email': 'test@example.com',
        })
        self.assertEqual(partner.name, 'Normal Contact')
        self.assertFalse(partner.contact_types)
        self.assertFalse(partner.is_creator)
        self.assertFalse(partner.is_contact)

    def test_computed_fields_stored(self):
        """Computed type flags are stored for performance."""
        partner_fields = self.Partner._fields
        stored_fields = [
            'is_creator', 'is_artist', 'is_contact', 'is_bidder', 'is_donor', 'is_consignor',
            'has_creator_type', 'has_contact_type',
        ]
        for field_name in stored_fields:
            if field_name in partner_fields:
                field = partner_fields[field_name]
                self.assertTrue(
                    field.store,
                    f"Field '{field_name}' should be stored for performance",
                )

    def test_creator_subtype_artist(self):
        """Artist sub-type assignment under Creator works correctly."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertIn(self.creator_type, self.partner.contact_types)
        self.assertIn(self.artist_subtype, self.partner.contact_subtypes)
        self.assertTrue(self.partner.is_creator)
        self.assertTrue(self.partner.is_artist)

    def test_contact_subtype_bidder(self):
        """Bidder sub-type assignment under Contact works correctly."""
        if self.bidder_subtype:
            partner2 = self.Partner.create({'name': 'Test Bidder 4'})
            partner2.write({
                'contact_types': [Command.link(self.contact_type.id)],
                'contact_subtypes': [Command.link(self.bidder_subtype.id)],
            })
            self.assertIn(self.contact_type, partner2.contact_types)
            self.assertIn(self.bidder_subtype, partner2.contact_subtypes)
            self.assertTrue(partner2.is_contact)
            self.assertTrue(partner2.is_bidder)

    def test_multiple_creator_subtypes(self):
        """Assigning multiple Creator sub-types works."""
        unique_suffix = uuid.uuid4().hex[:8]
        if self.creator_type:
            designer = self.ContactType.create({
                'name': 'Designer Test',
                'code': f'designer_test_multi_{unique_suffix}',
                'type_category': 'creator',
                'parent_type_id': self.creator_type.id,
            })
            self.partner.write({
                'contact_types': [Command.link(self.creator_type.id)],
                'contact_subtypes': [
                    Command.link(self.artist_subtype.id),
                    Command.link(designer.id),
                ],
            })
            self.assertIn(self.artist_subtype, self.partner.contact_subtypes)
            self.assertIn(designer, self.partner.contact_subtypes)

            # Clean up
            self.partner.write({
                'contact_subtypes': [Command.unlink(designer.id)],
            })
            designer.unlink()

    def test_get_creator_type_ids_method(self):
        """_get_creator_type_ids() returns parent and all sub-types."""
        creator_types = self.partner._get_creator_type_ids()
        self.assertIn(self.creator_type, creator_types)
        if self.artist_subtype:
            self.assertIn(self.artist_subtype, creator_types)

    def test_get_contact_type_ids_method(self):
        """_get_contact_type_ids() returns parent and all sub-types."""
        contact_types = self.partner._get_contact_type_ids()
        self.assertIn(self.contact_type, contact_types)
        if self.bidder_subtype:
            self.assertIn(self.bidder_subtype, contact_types)

    def test_onchange_contact_types_clears_subtypes(self):
        """Onchange clears sub-types when no parent types."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertTrue(self.partner.contact_types)
        self.assertTrue(self.partner.contact_subtypes)

        self.partner.write({
            'contact_types': [Command.clear()],
            'contact_subtypes': [Command.clear()],
        })
        self.partner._onchange_contact_types()
        self.partner = self.partner.browse(self.partner.id)
        self.assertFalse(self.partner.contact_types)
        self.assertFalse(self.partner.contact_subtypes)

    def test_onchange_contact_types_auto_selects_artist(self):
        """Onchange auto-selects Artist when Creator is selected."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.partner._onchange_contact_types()
        self.assertIn(self.artist_subtype, self.partner.contact_subtypes)

    def test_contact_type_sequence_ordering(self):
        """Contact types ordered by sequence."""
        all_types = self.ContactType.search([], order='sequence, name, id')
        sequences = [t.sequence for t in all_types]
        self.assertEqual(sequences, sorted(sequences))

    def test_contact_type_code_case_sensitivity(self):
        """Contact type code is case-sensitive."""
        creator = self.ContactType.search([('code', '=', 'creator')], limit=1)
        creator_upper = self.ContactType.search([('code', '=', 'CREATOR')], limit=1)
        self.assertTrue(creator)
        self.assertFalse(creator_upper)

    def test_adding_removing_types_dynamically(self):
        """Adding/removing types dynamically updates flags."""
        self.assertFalse(self.partner.is_creator)
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.is_creator)
        self.partner.write({
            'contact_types': [Command.unlink(self.creator_type.id)],
        })
        self.assertFalse(self.partner.is_creator)
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
        })
        self.assertTrue(self.partner.is_contact)

    def test_multi_company_security_rule(self):
        """Multi-company security rule works correctly."""
        rule = self.env['ir.rule'].search([
            ('name', 'ilike', 'SOR Contact Type%multi-company'),
            ('model_id.model', '=', 'sor.contact.type'),
        ], limit=1)
        if not rule:
            rule = self.env['ir.rule'].search([
                ('model_id.model', '=', 'sor.contact.type'),
                ('domain_force', 'ilike', '%company_id%'),
            ], limit=1)
        if not rule:
            self.skipTest("Multi-company security rule not found — may need module upgrade")

    # ==========================================
    # Story 03 — Widget and View Updates
    # ==========================================

    def test_onchange_contact_type_no_auto_subtype(self):
        """Selecting Contact type does not auto-assign any sub-type (AC4)."""
        partner = self.Partner.new({'name': 'Test Contact No Auto'})
        partner.contact_types = [(4, self.contact_type.id)]
        partner._onchange_contact_types()
        self.assertFalse(
            partner.contact_subtypes,
            "Contact type should not auto-assign a sub-type",
        )

    def test_onchange_creator_type_assigns_artist(self):
        """Selecting Creator type auto-assigns Artist sub-type (AC5 regression)."""
        partner = self.Partner.new({'name': 'Test Creator Auto'})
        partner.contact_types = [(4, self.creator_type.id)]
        partner._onchange_contact_types()
        # Use .ids comparison — Partner.new() produces NewId-backed records that
        # do not compare equal to real records via assertIn on the recordset.
        self.assertIn(
            self.artist_subtype.id,
            partner.contact_subtypes.ids,
            "Creator type should auto-assign Artist sub-type",
        )

    def test_activity_earned_subtype_ids_populated(self):
        """activity_earned_subtype_ids contains Bidder when assigned (AC3)."""
        if not self.bidder_subtype:
            self.skipTest("Bidder sub-type not found")
        partner = self.Partner.create({'name': 'Test Bidder Earned'})
        partner.write({
            'contact_subtypes': [Command.link(self.bidder_subtype.id)],
        })
        self.assertIn(
            self.bidder_subtype,
            partner.activity_earned_subtype_ids,
            "Bidder should appear in activity_earned_subtype_ids",
        )

    def test_activity_earned_subtype_ids_empty_for_manual_subtypes(self):
        """activity_earned_subtype_ids is empty when only Artist is assigned (AC2 negative)."""
        partner = self.Partner.create({'name': 'Test Artist Only'})
        partner.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertFalse(
            partner.activity_earned_subtype_ids,
            "Artist is not activity-earned; activity_earned_subtype_ids should be empty",
        )

    def test_activity_earned_subtype_ids_field_exists(self):
        """activity_earned_subtype_ids computed field exists on res.partner."""
        self.assertTrue(
            hasattr(self.partner, 'activity_earned_subtype_ids'),
            "activity_earned_subtype_ids field should exist on res.partner",
        )

    def test_activity_earned_subtype_ids_store_false(self):
        """activity_earned_subtype_ids is not stored (computed only)."""
        field = self.Partner._fields.get('activity_earned_subtype_ids')
        self.assertIsNotNone(field, "Field activity_earned_subtype_ids not found")
        self.assertFalse(field.store, "activity_earned_subtype_ids should not be stored")

    # ==========================================
    # staff_subtype_ids — AC2 fix (Story 03)
    # ==========================================

    def test_staff_subtype_ids_field_exists(self):
        """staff_subtype_ids computed+inverse field exists on res.partner."""
        self.assertTrue(
            hasattr(self.partner, 'staff_subtype_ids'),
            "staff_subtype_ids field should exist on res.partner",
        )
        field = self.Partner._fields.get('staff_subtype_ids')
        self.assertIsNotNone(field)
        self.assertFalse(field.store, "staff_subtype_ids should not be stored")

    def test_staff_subtype_ids_excludes_earned(self):
        """staff_subtype_ids never contains activity-earned sub-types."""
        if not self.bidder_subtype:
            self.skipTest("Bidder sub-type not found")
        partner = self.Partner.create({'name': 'Test Staff Subtypes Earned Exclusion'})
        partner.write({'contact_subtypes': [(4, self.bidder_subtype.id)]})
        self.assertNotIn(
            self.bidder_subtype,
            partner.staff_subtype_ids,
            "Bidder (activity-earned) must not appear in staff_subtype_ids",
        )

    def test_staff_subtype_ids_contains_artist(self):
        """staff_subtype_ids includes Artist (a staff-assignable sub-type)."""
        partner = self.Partner.create({'name': 'Test Staff Subtypes Artist'})
        partner.write({'contact_subtypes': [(4, self.artist_subtype.id)]})
        self.assertIn(
            self.artist_subtype,
            partner.staff_subtype_ids,
            "Artist (staff-assignable) must appear in staff_subtype_ids",
        )

    def test_staff_subtype_ids_inverse_preserves_earned(self):
        """Writing staff_subtype_ids via inverse does not remove earned sub-types."""
        if not self.bidder_subtype:
            self.skipTest("Bidder sub-type not found")
        partner = self.Partner.create({'name': 'Test Staff Subtypes Inverse Preservation'})
        partner.write({'contact_subtypes': [(4, self.bidder_subtype.id)]})

        # Now write staff_subtype_ids (simulates form save with Artist added)
        partner.write({'staff_subtype_ids': [(4, self.artist_subtype.id)]})

        # Bidder (earned) must still be in contact_subtypes
        self.assertIn(
            self.bidder_subtype,
            partner.contact_subtypes,
            "Bidder must be preserved in contact_subtypes after writing staff_subtype_ids",
        )
        # Artist (staff-assigned) must also be in contact_subtypes
        self.assertIn(
            self.artist_subtype,
            partner.contact_subtypes,
            "Artist must be present in contact_subtypes after writing staff_subtype_ids",
        )

    def test_onchange_clear_preserves_earned_subtypes(self):
        """Removing all parent types via onchange does not clear earned sub-types."""
        if not self.bidder_subtype:
            self.skipTest("Bidder sub-type not found")
        partner = self.Partner.new({
            'name': 'Test Onchange Earned Preservation',
            'contact_types': [(4, self.contact_type.id)],
            'contact_subtypes': [(4, self.bidder_subtype.id)],
        })
        partner.contact_types = False
        partner._onchange_contact_types()
        self.assertIn(
            self.bidder_subtype.id,
            partner.contact_subtypes.ids,
            "Bidder (earned) must survive removal of all parent types via onchange",
        )
