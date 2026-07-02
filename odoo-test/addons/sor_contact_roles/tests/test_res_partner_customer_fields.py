# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartnerContactFields(TransactionCase):
    """Test Contact-type-specific fields on res.partner (formerly Customer fields)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']

        # Get contact types (Contact replaced Customer)
        cls.contact_type = cls.ContactType.search([
            ('code', '=', 'contact'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.bidder_subtype = cls.ContactType.search([
            ('code', '=', 'bidder'),
            ('parent_type_id', '!=', False),
        ], limit=1)

        # Create a creator/artist for preferred_artist_ids
        cls.creator_type = cls.ContactType.search([
            ('code', '=', 'creator'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.artist_subtype = cls.ContactType.search([
            ('code', '=', 'artist'),
            ('parent_type_id', '!=', False),
        ], limit=1)

        cls.partner = cls.Partner.create({'name': 'Test Contact Partner'})

        # Create an artist partner
        cls.artist_partner = cls.Partner.create({'name': 'Test Artist'})
        cls.artist_partner.write({
            'contact_subtypes': [Command.link(cls.artist_subtype.id)],
        })

    def test_collection_focus_field_exists(self):
        """collection_focus field exists and accepts text."""
        self.assertTrue(hasattr(self.partner, 'collection_focus'))
        self.partner.collection_focus = 'Modern art and contemporary pieces.'
        self.assertEqual(self.partner.collection_focus, 'Modern art and contemporary pieces.')

    def test_preferred_artist_ids_field_exists(self):
        """preferred_artist_ids Many2many field exists."""
        self.assertTrue(hasattr(self.partner, 'preferred_artist_ids'))

        # Assign Contact type
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
        })

        # Assign preferred artists
        self.partner.preferred_artist_ids = [Command.link(self.artist_partner.id)]
        self.assertIn(self.artist_partner, self.partner.preferred_artist_ids)

    def test_contact_fields_visible_with_contact_type(self):
        """Contact fields visible when Contact type assigned."""
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
        })
        self.assertTrue(self.partner.has_contact_type)

        # Fields should be accessible
        self.partner.collection_focus = 'Test collection focus'
        self.partner.preferred_artist_ids = [Command.link(self.artist_partner.id)]

        self.assertEqual(self.partner.collection_focus, 'Test collection focus')
        self.assertIn(self.artist_partner, self.partner.preferred_artist_ids)

    def test_contact_fields_visible_with_bidder_subtype(self):
        """Contact fields visible when a Contact sub-type (Bidder) is assigned."""
        if not self.bidder_subtype:
            self.skipTest("Bidder sub-type not found")
        partner2 = self.Partner.create({'name': 'Test Bidder'})
        partner2.write({
            'contact_subtypes': [Command.link(self.bidder_subtype.id)],
        })
        self.assertTrue(partner2.has_contact_type)

        # Fields should be accessible
        partner2.collection_focus = 'Bidder collection focus'
        partner2.preferred_artist_ids = [Command.link(self.artist_partner.id)]

        self.assertEqual(partner2.collection_focus, 'Bidder collection focus')
        self.assertIn(self.artist_partner, partner2.preferred_artist_ids)

    def test_contact_fields_hidden_without_contact_type(self):
        """has_contact_type is False when no Contact type."""
        # Partner has no types
        self.assertFalse(self.partner.has_contact_type)

        # Fields still exist but has_contact_type should be False
        self.partner.collection_focus = 'Should still work'
        self.assertEqual(self.partner.collection_focus, 'Should still work')

    def test_contact_fields_data_persistence(self):
        """Contact field data persists after save."""
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
            'collection_focus': 'Persistent collection focus',
            'preferred_artist_ids': [Command.link(self.artist_partner.id)],
        })

        # Reload from database
        partner_reloaded = self.Partner.browse(self.partner.id)
        self.assertEqual(partner_reloaded.collection_focus, 'Persistent collection focus')
        self.assertIn(self.artist_partner, partner_reloaded.preferred_artist_ids)

    def test_preferred_artist_relationship(self):
        """preferred_artist_ids Many2many relationship works."""
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
            'preferred_artist_ids': [Command.link(self.artist_partner.id)],
        })
        self.assertIn(self.artist_partner, self.partner.preferred_artist_ids)

    def test_preferred_artist_junction_table(self):
        """Junction table sor_contact_preferred_artist_rel created correctly."""
        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
            'preferred_artist_ids': [Command.link(self.artist_partner.id)],
        })

        self.assertIn(self.artist_partner, self.partner.preferred_artist_ids)

        # Remove and verify it's removed
        self.partner.preferred_artist_ids = [Command.unlink(self.artist_partner.id)]
        self.assertNotIn(self.artist_partner, self.partner.preferred_artist_ids)
