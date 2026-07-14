# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartnerIntegration(TransactionCase):
    """Integration tests for complete contact type workflows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']
        cls.SocialMedia = cls.env['sor.contact.social.media']
        cls.Country = cls.env['res.country']

        # Get contact types — new hierarchy
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

        # Get country
        cls.country = cls.Country.search([], limit=1)
        if not cls.country:
            cls.country = cls.Country.create({
                'name': 'Test Country',
                'code': 'TC',
            })

    def test_contact_type_assignment_workflow(self):
        """Complete workflow: create contact → assign types → verify fields."""
        partner = self.Partner.create({'name': 'Integration Test Contact'})

        partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(partner.is_creator)
        self.assertTrue(partner.has_creator_type)

        partner.write({
            'biography': 'Test biography',
            'birth_year': '1990',
            'creator_website': 'https://example.com',
        })
        if self.country:
            partner.nationality = self.country.id

        self.assertEqual(partner.biography, 'Test biography')
        self.assertEqual(partner.birth_year, '1990')
        self.assertEqual(partner.creator_website, 'https://example.com')

    def test_creator_workflow_with_social_media(self):
        """Creator workflow: assign Creator → add social media → verify."""
        partner = self.Partner.create({'name': 'Creator with Social Media'})

        partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })

        social_media = self.SocialMedia.create({
            'partner_id': partner.id,
            'platform': 'instagram',
            'handle': 'test_creator',
        })
        self.assertIn(social_media, partner.social_media_ids)
        self.assertEqual(social_media.url, 'https://www.instagram.com/test_creator')

        self.SocialMedia.create({
            'partner_id': partner.id,
            'platform': 'facebook',
            'handle': 'testcreator',
        })
        self.assertEqual(len(partner.social_media_ids), 2)

    def test_contact_workflow_with_preferred_artists(self):
        """Contact workflow: assign Contact → add preferred artists → verify."""
        artist = self.Partner.create({'name': 'Test Artist'})
        artist.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })

        contact = self.Partner.create({'name': 'Test Contact Partner'})
        contact.write({
            'contact_types': [Command.link(self.contact_type.id)],
        })
        contact.write({
            'collection_focus': 'Modern art collection',
            'preferred_artist_ids': [Command.link(artist.id)],
        })

        self.assertTrue(contact.is_contact)
        self.assertEqual(contact.collection_focus, 'Modern art collection')
        self.assertIn(artist, contact.preferred_artist_ids)

    def test_multi_type_contact_workflow(self):
        """Multi-type contact: Creator + Contact → verify all fields visible."""
        partner = self.Partner.create({'name': 'Multi-Type Contact'})

        partner.write({
            'contact_types': [
                Command.link(self.creator_type.id),
                Command.link(self.contact_type.id),
            ],
        })
        self.assertTrue(partner.is_creator)
        self.assertTrue(partner.is_contact)
        self.assertTrue(partner.has_creator_type)
        self.assertTrue(partner.has_contact_type)

        partner.biography = 'Creator biography'
        partner.birth_year = '1985'
        partner.collection_focus = 'Art collection focus'

        self.assertEqual(partner.biography, 'Creator biography')
        self.assertEqual(partner.birth_year, '1985')
        self.assertEqual(partner.collection_focus, 'Art collection focus')

    def test_subtype_onchange_workflow(self):
        """Subtype workflow: assign Creator → auto-select Artist via onchange → verify."""
        partner = self.Partner.create({'name': 'Subtype Onchange Test'})

        partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        partner._onchange_contact_types()

        self.assertIn(self.artist_subtype, partner.contact_subtypes)
        self.assertTrue(partner.is_artist)
        self.assertTrue(partner.is_creator)

        partner.biography = 'Artist biography'
        self.assertEqual(partner.biography, 'Artist biography')

    def test_complete_creator_contact_workflow(self):
        """Complete workflow with both Creator and Contact sub-types."""
        # Create artist
        artist = self.Partner.create({'name': 'Test Artist'})
        artist.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
            'biography': 'Artist biography',
            'birth_year': 1980,
        })

        # Create bidder
        bidder = self.Partner.create({'name': 'Test Bidder'})
        if self.bidder_subtype:
            bidder.write({
                'contact_subtypes': [Command.link(self.bidder_subtype.id)],
                'collection_focus': 'Contemporary art',
                'preferred_artist_ids': [Command.link(artist.id)],
            })

            # Verify bidder
            self.assertTrue(bidder.is_contact)
            self.assertTrue(bidder.is_bidder)
            self.assertEqual(bidder.collection_focus, 'Contemporary art')
            self.assertIn(artist, bidder.preferred_artist_ids)

        # Verify artist
        self.assertTrue(artist.is_creator)
        self.assertTrue(artist.is_artist)
        self.assertEqual(artist.biography, 'Artist biography')
