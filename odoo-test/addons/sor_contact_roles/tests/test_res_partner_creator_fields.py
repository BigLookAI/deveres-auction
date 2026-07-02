# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartnerCreatorFields(TransactionCase):
    """Test Creator-specific fields on res.partner."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']
        cls.Country = cls.env['res.country']

        # Get contact types
        cls.creator_type = cls.ContactType.search([
            ('code', '=', 'creator'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.artist_subtype = cls.ContactType.search([
            ('code', '=', 'artist'),
            ('parent_type_id', '!=', False),
        ], limit=1)

        # Get a country for nationality
        cls.country = cls.Country.search([], limit=1)
        if not cls.country:
            cls.country = cls.Country.create({
                'name': 'Test Country',
                'code': 'TC',
            })

        cls.partner = cls.Partner.create({'name': 'Test Creator'})

    def test_biography_field_exists(self):
        """Test biography field exists and accepts text."""
        self.assertTrue(hasattr(self.partner, 'biography'))
        self.partner.biography = 'This is a test biography.'
        self.assertEqual(self.partner.biography, 'This is a test biography.')

    def test_birth_date_field_exists(self):
        """Test birth_date field exists and accepts date."""
        self.assertTrue(hasattr(self.partner, 'birth_date'))
        test_date = date(1990, 1, 1)
        self.partner.birth_date = test_date
        self.assertEqual(self.partner.birth_date, test_date)

    def test_nationality_field_exists(self):
        """Test nationality field exists and links to res.country."""
        self.assertTrue(hasattr(self.partner, 'nationality'))
        if self.country:
            self.partner.nationality = self.country.id
            self.assertEqual(self.partner.nationality, self.country)

    def test_creator_website_field_exists(self):
        """Test creator_website field exists and accepts URL (max 512 chars)."""
        self.assertTrue(hasattr(self.partner, 'creator_website'))
        test_url = 'https://www.example.com'
        self.partner.creator_website = test_url
        self.assertEqual(self.partner.creator_website, test_url)

        # Test max length (512 chars) - field may truncate
        long_url = 'https://www.' + 'a' * 500 + '.com'
        self.partner.creator_website = long_url
        # Field may truncate to 512 chars, so check it's at most 512
        self.assertLessEqual(len(self.partner.creator_website), 512)
        # And check it's not empty
        self.assertGreater(len(self.partner.creator_website), 0)

    def test_creator_fields_visible_with_creator_type(self):
        """Test Creator fields visible when Creator type assigned."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.has_creator_type)

        # Fields should be accessible
        self.partner.biography = 'Test biography'
        self.partner.birth_date = date(1990, 1, 1)
        self.partner.creator_website = 'https://example.com'
        if self.country:
            self.partner.nationality = self.country.id

        self.assertEqual(self.partner.biography, 'Test biography')
        self.assertEqual(self.partner.birth_date, date(1990, 1, 1))
        self.assertEqual(self.partner.creator_website, 'https://example.com')

    def test_creator_fields_visible_with_artist_subtype(self):
        """Test Creator fields visible when Artist sub-type assigned."""
        partner2 = self.Partner.create({'name': 'Test Artist'})
        partner2.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertTrue(partner2.has_creator_type)

        # Fields should be accessible
        partner2.biography = 'Artist biography'
        partner2.birth_date = date(1985, 5, 15)
        self.assertEqual(partner2.biography, 'Artist biography')
        self.assertEqual(partner2.birth_date, date(1985, 5, 15))

    def test_creator_fields_hidden_without_creator_type(self):
        """Test Creator fields hidden when no Creator type."""
        # Partner has no types
        self.assertFalse(self.partner.has_creator_type)

        # Fields should still exist but has_creator_type should be False
        # (Field visibility is controlled by attrs in views, not model level)
        self.partner.biography = 'Should still work'
        self.assertEqual(self.partner.biography, 'Should still work')

    def test_creator_fields_data_persistence(self):
        """Test Creator field data persists after save."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
            'biography': 'Persistent biography',
            'birth_date': date(1990, 1, 1),
            'creator_website': 'https://persistent.com',
        })
        if self.country:
            self.partner.nationality = self.country.id

        # Reload from database
        partner_reloaded = self.Partner.browse(self.partner.id)
        self.assertEqual(partner_reloaded.biography, 'Persistent biography')
        self.assertEqual(partner_reloaded.birth_date, date(1990, 1, 1))
        self.assertEqual(partner_reloaded.creator_website, 'https://persistent.com')
        if self.country:
            self.assertEqual(partner_reloaded.nationality, self.country)

    def test_nationality_domain_filtering(self):
        """Test nationality field domain (res.country)."""
        # Nationality should only accept res.country records
        countries = self.Country.search([])
        self.assertTrue(len(countries) > 0)

        if self.country:
            self.partner.nationality = self.country.id
            self.assertEqual(self.partner.nationality._name, 'res.country')

    def test_social_media_one2many_relationship(self):
        """Test social_media_ids One2many relationship works."""
        self.assertTrue(hasattr(self.partner, 'social_media_ids'))

        # Assign Creator type
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Create social media record
        social_media = self.env['sor.contact.social.media'].create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': 'test_artist',
        })

        # Verify relationship
        self.assertIn(social_media, self.partner.social_media_ids)
        self.assertEqual(social_media.partner_id, self.partner)
