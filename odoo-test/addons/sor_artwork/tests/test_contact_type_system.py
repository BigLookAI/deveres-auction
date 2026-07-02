# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestContactTypeSystem(TransactionCase):
    """Unit tests for contact type system (creation, assignment, multiple types, computed fields, field visibility)."""

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
        cls.customer_type = cls.ContactType.search([
            ('code', '=', 'customer'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.advisor_type = cls.ContactType.search([
            ('code', '=', 'advisor'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.artist_subtype = cls.ContactType.search([
            ('code', '=', 'artist'),
            ('parent_type_id', '!=', False),
        ], limit=1)
        cls.private_collector_subtype = cls.ContactType.search([
            ('code', '=', 'private_collector'),
            ('parent_type_id', '!=', False),
        ], limit=1)

    def test_contact_type_creation(self):
        """Test contact type creation."""
        contact_type = self.ContactType.create({
            'name': 'Test Type',
            'code': 'test_type_creation',
            'type_category': 'other',
        })

        # Verify creation
        self.assertTrue(contact_type.exists())
        self.assertEqual(contact_type.name, 'Test Type')
        self.assertEqual(contact_type.code, 'test_type_creation')
        self.assertEqual(contact_type.type_category, 'other')

        # Clean up
        contact_type.unlink()

    def test_contact_type_assignment_single(self):
        """Test assigning a single contact type to a contact."""
        partner = self.Partner.create({
            'name': 'Test Contact Single',
        })

        # Assign Creator type
        partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Verify type is assigned
        self.assertIn(self.creator_type, partner.contact_types)
        self.assertTrue(partner.is_creator)

        # Clean up
        partner.unlink()

    def test_contact_type_assignment_multiple(self):
        """Test assigning multiple contact types to a contact."""
        partner = self.Partner.create({
            'name': 'Test Contact Multiple',
        })

        # Assign Creator and Advisor types
        partner.write({
            'contact_types': [
                Command.link(self.creator_type.id),
                Command.link(self.advisor_type.id),
            ],
        })

        # Verify both types are assigned
        self.assertIn(self.creator_type, partner.contact_types)
        self.assertIn(self.advisor_type, partner.contact_types)

        # Verify computed fields
        self.assertTrue(partner.is_creator)
        self.assertTrue(partner.is_advisor)

        # Clean up
        partner.unlink()

    def test_computed_fields_creator(self):
        """Test computed fields for Creator type."""
        partner = self.Partner.create({
            'name': 'Test Creator',
        })

        # Initially False
        self.assertFalse(partner.is_creator)
        self.assertFalse(partner.is_artist)

        # Assign Creator type
        partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Verify computed fields
        self.assertTrue(partner.is_creator)
        # is_artist may be True if Creator is treated as Artist

        # Clean up
        partner.unlink()

    def test_computed_fields_customer(self):
        """Test computed fields for Customer type."""
        partner = self.Partner.create({
            'name': 'Test Customer',
        })

        # Initially False
        self.assertFalse(partner.is_customer)

        # Assign Customer type
        partner.write({
            'contact_types': [Command.link(self.customer_type.id)],
        })

        # Verify computed fields
        self.assertTrue(partner.is_customer)

        # Clean up
        partner.unlink()

    def test_field_visibility_creator(self):
        """Test field visibility when Creator type is assigned."""
        partner = self.Partner.create({
            'name': 'Test Creator Fields',
        })

        # Initially has_creator_type should be False
        self.assertFalse(partner.has_creator_type)

        # Assign Creator type
        partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Verify has_creator_type is True (controls field visibility)
        self.assertTrue(partner.has_creator_type)

        # Creator-specific fields should be accessible
        partner.write({
            'biography': 'Test biography',
            'birth_date': '1990-01-01',
        })

        self.assertEqual(partner.biography, 'Test biography')
        self.assertEqual(partner.birth_date, fields.Date.from_string('1990-01-01'))

        # Clean up
        partner.unlink()

    def test_field_visibility_customer(self):
        """Test field visibility when Customer type is assigned."""
        partner = self.Partner.create({
            'name': 'Test Customer Fields',
        })

        # Initially has_customer_type should be False
        self.assertFalse(partner.has_customer_type)

        # Assign Customer type
        partner.write({
            'contact_types': [Command.link(self.customer_type.id)],
        })

        # Verify has_customer_type is True
        self.assertTrue(partner.has_customer_type)

        # Customer-specific fields should be accessible
        partner.write({
            'collection_focus': 'Modern art collection',
        })

        self.assertEqual(partner.collection_focus, 'Modern art collection')

        # Clean up
        partner.unlink()

    def test_subtype_assignment_auto_parent(self):
        """Test that parent type is auto-assigned when sub-type is assigned."""
        partner = self.Partner.create({
            'name': 'Test Subtype',
        })

        # Assign Artist sub-type without explicitly assigning parent
        partner.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })

        # Verify parent (Creator) is auto-assigned
        self.assertIn(self.creator_type, partner.contact_types)
        self.assertIn(self.artist_subtype, partner.contact_subtypes)

        # Verify computed fields
        self.assertTrue(partner.is_creator)
        self.assertTrue(partner.is_artist)

        # Clean up
        partner.unlink()

    def test_contact_without_types_normal_behavior(self):
        """Test that contacts without contact types behave like normal res.partner records."""
        partner = self.Partner.create({
            'name': 'Normal Contact',
            'email': 'normal@example.com',
            'phone': '123-456-7890',
        })

        # Verify no types assigned
        self.assertFalse(partner.contact_types)
        self.assertFalse(partner.contact_subtypes)

        # Verify computed fields are False
        self.assertFalse(partner.is_creator)
        self.assertFalse(partner.is_customer)
        self.assertFalse(partner.is_advisor)
        self.assertFalse(partner.has_creator_type)
        self.assertFalse(partner.has_customer_type)

        # Verify partner can be used normally
        self.assertEqual(partner.name, 'Normal Contact')
        self.assertEqual(partner.email, 'normal@example.com')
        self.assertEqual(partner.phone, '123-456-7890')

        # Verify partner can be updated normally
        partner.write({
            'name': 'Updated Normal Contact',
        })
        self.assertEqual(partner.name, 'Updated Normal Contact')

        # Clean up
        partner.unlink()

    def test_multiple_types_all_fields_visible(self):
        """Test that when multiple types are assigned, all relevant fields are visible."""
        partner = self.Partner.create({
            'name': 'Multi-Type Contact',
        })

        # Assign both Creator and Customer types
        partner.write({
            'contact_types': [
                Command.link(self.creator_type.id),
                Command.link(self.customer_type.id),
            ],
        })

        # Verify both type flags are True
        self.assertTrue(partner.has_creator_type)
        self.assertTrue(partner.has_customer_type)

        # Verify both sets of fields are accessible
        partner.write({
            'biography': 'Creator biography',
            'collection_focus': 'Customer collection',
        })

        self.assertEqual(partner.biography, 'Creator biography')
        self.assertEqual(partner.collection_focus, 'Customer collection')

        # Clean up
        partner.unlink()

    def test_computed_fields_update_on_type_change(self):
        """Test that computed fields update when contact types change."""
        partner = self.Partner.create({
            'name': 'Test Updates',
        })

        # Initially no types
        self.assertFalse(partner.is_creator)
        self.assertFalse(partner.is_customer)

        # Assign Creator
        partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(partner.is_creator)
        self.assertFalse(partner.is_customer)

        # Add Customer
        partner.write({
            'contact_types': [
                Command.link(self.creator_type.id),
                Command.link(self.customer_type.id),
            ],
        })
        self.assertTrue(partner.is_creator)
        self.assertTrue(partner.is_customer)

        # Remove Creator - use Command.set() to replace all types with just Customer
        partner.write({
            'contact_types': [Command.set([self.customer_type.id])],
        })
        # Stored computed fields should update automatically, but refresh to be sure
        partner.invalidate_recordset(['is_creator', 'is_customer'])
        self.assertFalse(partner.is_creator)
        self.assertTrue(partner.is_customer)

        # Clean up
        partner.unlink()
