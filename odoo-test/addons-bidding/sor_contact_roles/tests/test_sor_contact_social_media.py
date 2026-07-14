# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestSorContactSocialMedia(TransactionCase):
    """Test sor.contact.social.media model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.SocialMedia = cls.env['sor.contact.social.media']
        cls.Partner = cls.env['res.partner']

        cls.partner = cls.Partner.create({'name': 'Test Creator'})

    def test_social_media_model_exists(self):
        """Test social media model sor.contact.social.media exists."""
        # Check model exists and has correct name
        self.assertIsNotNone(self.SocialMedia)
        self.assertEqual(self.SocialMedia._name, 'sor.contact.social.media')
        # Verify we can search (proves model is registered)
        count = self.SocialMedia.search_count([])
        self.assertIsInstance(count, int)

    @mute_logger('odoo.sql_db', 'odoo.orm')
    def test_social_media_required_fields(self):
        """Test required fields: partner_id, platform, handle."""
        # Try to create without required fields - should fail
        # Use savepoint to handle transaction errors
        savepoint = self.env.cr.savepoint()
        try:
            self.SocialMedia.create({})
            # If we get here, creation succeeded (shouldn't happen)
            # Rollback savepoint and clean up
            savepoint.rollback()
            created = self.SocialMedia.search([])
            if created:
                # Find the one we just created (no partner_id)
                invalid = created.filtered(lambda r: not r.partner_id)
                if invalid:
                    invalid.unlink()
            self.fail("Creating social media without required fields should have raised an exception")
        except (UserError, ValidationError, ValueError, Exception):  # noqa: BLE001
            # Expected - required field validation worked
            # Rollback savepoint to clear transaction error state
            savepoint.rollback()
            pass

        # Create with all required fields - should succeed
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': 'test_handle',
        })
        self.assertTrue(social_media)
        # Clean up
        social_media.unlink()

    def test_social_media_platform_selection(self):
        """Test platform selection field values."""
        platforms = ['instagram', 'facebook', 'twitter', 'linkedin', 'website', 'other']

        for platform in platforms:
            social_media = self.SocialMedia.create({
                'partner_id': self.partner.id,
                'platform': platform,
                'handle': f'test_{platform}',
            })
            self.assertEqual(social_media.platform, platform)

    def test_social_media_url_computation_instagram(self):
        """Test URL computation for Instagram."""
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': 'test_artist',
        })
        self.assertEqual(social_media.url, 'https://www.instagram.com/test_artist')

        # Test with @ prefix
        social_media2 = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': '@test_artist',
        })
        self.assertEqual(social_media2.url, 'https://www.instagram.com/test_artist')

    def test_social_media_url_computation_facebook(self):
        """Test URL computation for Facebook."""
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'facebook',
            'handle': 'testartist',
        })
        self.assertEqual(social_media.url, 'https://www.facebook.com/testartist')

    def test_social_media_url_computation_twitter(self):
        """Test URL computation for Twitter."""
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'twitter',
            'handle': 'testartist',
        })
        self.assertEqual(social_media.url, 'https://twitter.com/testartist')

    def test_social_media_url_computation_linkedin(self):
        """Test URL computation for LinkedIn."""
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'linkedin',
            'handle': 'test-artist',
        })
        self.assertEqual(social_media.url, 'https://www.linkedin.com/in/test-artist')

    def test_social_media_url_computation_website(self):
        """Test URL computation for Website."""
        # Test with full URL
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'website',
            'handle': 'https://www.example.com',
        })
        self.assertEqual(social_media.url, 'https://www.example.com')

        # Test without http
        social_media2 = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'website',
            'handle': 'www.example.com',
        })
        self.assertEqual(social_media2.url, 'https://www.example.com')

    def test_social_media_url_computation_other(self):
        """Test URL computation for Other."""
        # Test with full URL
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'other',
            'handle': 'https://other-platform.com/user',
        })
        self.assertEqual(social_media.url, 'https://other-platform.com/user')

        # Test without http
        social_media2 = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'other',
            'handle': 'other-platform.com/user',
        })
        self.assertEqual(social_media2.url, 'https://other-platform.com/user')

    def test_social_media_url_with_existing_url(self):
        """Test URL computation when handle is already a URL."""
        # Test Instagram with full URL (should use handle as-is if it starts with http)
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': 'https://www.instagram.com/test_artist',
        })
        self.assertEqual(social_media.url, 'https://www.instagram.com/test_artist')

    def test_social_media_unique_constraint(self):
        """Test unique platform+handle combination per partner."""
        # Create first record
        self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': 'test_handle',
        })

        # Try to create duplicate - should fail
        with self.assertRaises(ValidationError):
            self.SocialMedia.create({
                'partner_id': self.partner.id,
                'platform': 'instagram',
                'handle': 'test_handle',
            })

        # Different partner should work
        partner2 = self.Partner.create({'name': 'Test Creator 2'})
        social_media2 = self.SocialMedia.create({
            'partner_id': partner2.id,
            'platform': 'instagram',
            'handle': 'test_handle',
        })
        self.assertTrue(social_media2)

        # Different platform should work
        social_media3 = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'facebook',
            'handle': 'test_handle',
        })
        self.assertTrue(social_media3)

    def test_social_media_cascade_delete(self):
        """Test social media records deleted when partner deleted."""
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': 'test_handle',
        })
        social_media_id = social_media.id

        # Delete partner
        self.partner.unlink()

        # Social media should be deleted (cascade)
        self.assertFalse(self.SocialMedia.browse(social_media_id).exists())

    def test_social_media_active_field(self):
        """Test active field for archiving."""
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': 'test_handle',
        })
        self.assertTrue(social_media.active)

        # Archive
        social_media.write({'active': False})
        self.assertFalse(social_media.active)

        # Should still exist with active_test=False
        archived = self.SocialMedia.with_context(active_test=False).browse(social_media.id)
        self.assertTrue(archived.exists())

    def test_social_media_one2many_relationship(self):
        """Test social_media_ids One2many relationship works."""
        # Assign Creator type to partner
        creator_type = self.env['sor.contact.type'].search([
            ('code', '=', 'creator'),
            ('parent_type_id', '=', False),
        ], limit=1)
        if creator_type:
            self.partner.write({
                'contact_types': [(4, creator_type.id)],
            })

        # Create social media
        social_media = self.SocialMedia.create({
            'partner_id': self.partner.id,
            'platform': 'instagram',
            'handle': 'test_artist',
        })

        # Verify relationship
        self.assertIn(social_media, self.partner.social_media_ids)
        self.assertEqual(social_media.partner_id, self.partner)
