# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCreatorArtworkRelationship(TransactionCase):
    """Unit tests for creator-painting relationship (creation, validation, computed fields, deletion constraints)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']
        cls.ProductTemplate = cls.env['product.template']

        # Get Creator contact type
        cls.creator_type = cls.ContactType.search([
            ('code', '=', 'creator'),
            ('parent_type_id', '=', False),
        ], limit=1)

        # Create a creator/artist
        cls.creator = cls.Partner.create({
            'name': 'Test Artist',
            'contact_types': [Command.link(cls.creator_type.id)],
        })

        # Create a non-creator contact
        cls.non_creator = cls.Partner.create({
            'name': 'Regular Contact',
        })

    def test_artwork_creation_with_creator(self):
        """Test creating artwork with creator_id field."""
        artwork = self.ProductTemplate.create({
            'name': 'Test Painting',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        # Verify creation
        self.assertTrue(artwork.exists())
        self.assertEqual(artwork.creator_id, self.creator)
        self.assertEqual(artwork.product_type, 'artwork')
        self.assertEqual(artwork.product_subtype, 'painting')

        # Clean up
        artwork.unlink()

    def test_creator_id_domain_filter(self):
        """Test that creator_id domain filter only shows contacts with is_creator=True."""
        # Verify creator is selectable (has is_creator=True)
        self.assertTrue(self.creator.is_creator)

        # Create artwork and verify creator can be selected
        artwork = self.ProductTemplate.create({
            'name': 'Test Artwork',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        self.assertEqual(artwork.creator_id, self.creator)

        # Verify non-creator is not in domain
        # The domain filter should prevent non-creators from being selected
        # We can test this by trying to set a non-creator (should work at ORM level but domain prevents in UI)
        self.assertFalse(self.non_creator.is_creator)

        # Clean up
        artwork.unlink()

    def test_artwork_ids_computed_field(self):
        """Test artwork_ids computed field on res.partner."""
        # Create artwork with creator
        artwork = self.ProductTemplate.create({
            'name': 'Test Painting 1',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        # Verify artwork_ids field exists and artwork is included
        self.assertTrue(hasattr(self.creator, 'artwork_ids'))
        self.assertIn(artwork, self.creator.artwork_ids)
        self.assertEqual(len(self.creator.artwork_ids), 1)

        # Verify artwork_count is computed correctly
        self.assertTrue(hasattr(self.creator, 'artwork_count'))
        self.assertEqual(self.creator.artwork_count, 1)

        # Create another artwork
        artwork2 = self.ProductTemplate.create({
            'name': 'Test Painting 2',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 40.0,
            'dimensions_height': 50.0,
            'creator_id': self.creator.id,
        })

        # Refresh to recompute
        self.creator.invalidate_recordset(['artwork_ids', 'artwork_count'])

        # Verify both artworks are in creator's artwork_ids
        self.assertIn(artwork, self.creator.artwork_ids)
        self.assertIn(artwork2, self.creator.artwork_ids)
        self.assertEqual(len(self.creator.artwork_ids), 2)
        self.assertEqual(self.creator.artwork_count, 2)

        # Clean up
        artwork2.unlink()
        artwork.unlink()

    def test_creator_required_validation(self):
        """Test creator required validation for artworks."""
        # Try to create artwork without creator_id - should raise ValidationError
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create({
                'name': 'Artwork Without Creator',
                'product_type': 'artwork',
                'product_subtype': 'painting',
                'dimensions_width': 50.0,
                'dimensions_height': 60.0,
                # creator_id intentionally omitted
            })

        # Verify error message mentions creator
        error_msg = str(cm.exception).lower()
        self.assertIn('creator', error_msg)

    def test_creator_computed_fields_update(self):
        """Test that creator relationship updates computed fields correctly."""
        # Create artwork with creator
        artwork = self.ProductTemplate.create({
            'name': 'Test Artwork',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        # Verify artwork has creator
        self.assertEqual(artwork.creator_id, self.creator)

        # Verify artwork_ids is updated
        self.assertIn(artwork, self.creator.artwork_ids)
        self.assertEqual(self.creator.artwork_count, 1)

        # Change creator
        creator2 = self.Partner.create({
            'name': 'Another Artist',
            'contact_types': [Command.link(self.creator_type.id)],
        })

        artwork.write({
            'creator_id': creator2.id,
        })

        # Refresh to recompute
        self.creator.invalidate_recordset(['artwork_ids', 'artwork_count'])
        creator2.invalidate_recordset(['artwork_ids', 'artwork_count'])

        # Verify creator changed
        self.assertEqual(artwork.creator_id, creator2)

        # Verify artwork_ids is updated for both creators
        self.assertNotIn(artwork, self.creator.artwork_ids)
        self.assertEqual(self.creator.artwork_count, 0)
        self.assertIn(artwork, creator2.artwork_ids)
        self.assertEqual(creator2.artwork_count, 1)

        # Clean up
        artwork.unlink()
        creator2.unlink()

    def test_deletion_constraints(self):
        """Test deletion constraints (prevent deletion if artworks exist)."""
        # Create artwork with creator
        artwork = self.ProductTemplate.create({
            'name': 'Test Artwork',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        # Try to delete creator - should raise ValidationError
        with self.assertRaises(ValidationError) as cm:
            self.creator.unlink()

        # Verify error message mentions artworks
        error_msg = str(cm.exception).lower()
        self.assertIn('artwork', error_msg)

        # Verify artwork still exists
        self.assertTrue(artwork.exists())

        # Delete artwork first, then creator should be deletable
        artwork.unlink()
        self.creator.unlink()

        # Recreate creator for other tests
        self.creator = self.Partner.create({
            'name': 'Test Artist',
            'contact_types': [Command.link(self.creator_type.id)],
        })

    def test_multiple_artworks_same_creator(self):
        """Test that multiple artworks can be linked to the same creator."""
        # Create multiple artworks with same creator
        artwork1 = self.ProductTemplate.create({
            'name': 'Painting 1',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        artwork2 = self.ProductTemplate.create({
            'name': 'Painting 2',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 40.0,
            'dimensions_height': 50.0,
            'creator_id': self.creator.id,
        })

        artwork3 = self.ProductTemplate.create({
            'name': 'Sculpture 1',
            'product_type': 'artwork',
            'product_subtype': 'sculpture',
            'dimensions_width': 30.0,
            'dimensions_height': 40.0,
            'dimensions_depth': 20.0,
            'creator_id': self.creator.id,
        })

        # Verify all artworks have same creator
        self.assertEqual(artwork1.creator_id, self.creator)
        self.assertEqual(artwork2.creator_id, self.creator)
        self.assertEqual(artwork3.creator_id, self.creator)

        # Refresh to recompute
        self.creator.invalidate_recordset(['artwork_ids', 'artwork_count'])

        # Verify all are included in artwork_ids
        self.assertIn(artwork1, self.creator.artwork_ids)
        self.assertIn(artwork2, self.creator.artwork_ids)
        self.assertIn(artwork3, self.creator.artwork_ids)
        self.assertEqual(len(self.creator.artwork_ids), 3)
        self.assertEqual(self.creator.artwork_count, 3)

        # Clean up
        artwork1.unlink()
        artwork2.unlink()
        artwork3.unlink()

    def test_artwork_creator_navigation(self):
        """Test navigation from artwork to creator."""
        artwork = self.ProductTemplate.create({
            'name': 'Test Artwork',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        # Verify navigation works
        self.assertEqual(artwork.creator_id, self.creator)
        self.assertEqual(artwork.creator_id.name, 'Test Artist')

        # Verify we can access creator fields
        self.assertTrue(artwork.creator_id.is_creator)

        # Clean up
        artwork.unlink()

    def test_creator_validation_non_creator(self):
        """Test that non-creator contacts cannot be assigned as creator."""
        # Try to assign non-creator as creator - should raise ValidationError
        artwork = self.ProductTemplate.create({
            'name': 'Test Artwork',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,  # Valid creator first
        })

        # Try to change to non-creator
        with self.assertRaises(ValidationError) as cm:
            artwork.write({
                'creator_id': self.non_creator.id,
            })

        # Verify error message mentions creator/artist type
        error_msg = str(cm.exception).lower()
        self.assertTrue('creator' in error_msg or 'artist' in error_msg)

        # Clean up
        artwork.unlink()

    def test_action_view_artworks(self):
        """Test action_view_artworks method on creator."""
        # Create artworks with creator
        artwork1 = self.ProductTemplate.create({
            'name': 'Artwork 1',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        artwork2 = self.ProductTemplate.create({
            'name': 'Artwork 2',
            'product_type': 'artwork',
            'product_subtype': 'sculpture',
            'dimensions_width': 30.0,
            'dimensions_height': 40.0,
            'dimensions_depth': 20.0,
            'creator_id': self.creator.id,
        })

        # Call action method
        action = self.creator.action_view_artworks()

        # Verify action structure
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'product.template')
        self.assertIn('list', action['view_mode'])

        # Verify domain filters artworks by creator
        domain = action['domain']
        self.assertIn(('product_type', '=', 'artwork'), domain)
        self.assertIn(('creator_id', '=', self.creator.id), domain)

        # Verify context has default values
        context = action['context']
        self.assertEqual(context.get('default_product_type'), 'artwork')
        self.assertEqual(context.get('default_creator_id'), self.creator.id)

        # Clean up
        artwork1.unlink()
        artwork2.unlink()
