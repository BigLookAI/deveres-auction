# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestArtworkFieldsValidations(TransactionCase):
    """Unit tests for artwork fields and validations (all fields, creation_year validation, artwork_type, dimensions, certificates, images)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.ProductTemplate = cls.env['product.template']
        cls.ArtworkImage = cls.env['sor.art.work.image']

        cls.creator = cls.Partner.create({'name': 'Test Artist'})
        # When sor_artwork_contact_roles is installed, creator_id requires Creator/Artist type.
        # Assign the Creator parent type if the contact type model is available.
        ContactType = cls.env.get('sor.contact.type')
        if ContactType is not None:
            creator_type = ContactType.search([('code', '=', 'creator')], limit=1)
            if creator_type:
                cls.creator.contact_types = [(4, creator_type.id)]

    def test_all_artwork_fields(self):
        """Test that all artwork-specific fields exist and can be set."""
        artwork = self.ProductTemplate.create({
            'name': 'Complete Artwork',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'medium': 'Oil on canvas',
            'creation_year': 2020,
            'condition': 'Excellent condition',
            'provenance': 'Private collection',
            'certificate_of_authenticity': True,
            'creator_id': self.creator.id,
        })

        # Verify all fields
        self.assertEqual(artwork.product_type, 'artwork')
        self.assertEqual(artwork.product_subtype, 'painting')
        self.assertEqual(artwork.dimensions_width, 50.0)
        self.assertEqual(artwork.dimensions_height, 60.0)
        self.assertEqual(artwork.medium, 'Oil on canvas')
        self.assertEqual(artwork.creation_year, 2020)
        self.assertEqual(artwork.condition, 'Excellent condition')
        self.assertEqual(artwork.provenance, 'Private collection')
        self.assertTrue(artwork.certificate_of_authenticity)
        self.assertEqual(artwork.creator_id, self.creator)

        # Clean up
        artwork.unlink()

    def test_creation_year_validation_valid_range(self):
        """Test creation_year validation with valid years."""
        # Test valid years
        valid_years = [1000, 1500, 1800, 2000, 2024, 2100]

        for year in valid_years:
            artwork = self.ProductTemplate.create({
                'name': f'Artwork {year}',
                'product_type': 'artwork',
                'product_subtype': 'painting',
                'dimensions_width': 50.0,
                'dimensions_height': 60.0,
                'creation_year': year,
                'creator_id': self.creator.id,
            })

            self.assertEqual(artwork.creation_year, year)
            artwork.unlink()

    def test_creation_year_validation_invalid_too_early(self):
        """Test creation_year validation with year before 1000."""
        # Try to create artwork with year < 1000
        # Constraint is automatically called on create/write
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create({
                'name': 'Old Artwork',
                'product_type': 'artwork',
                'product_subtype': 'painting',
                'dimensions_width': 50.0,
                'dimensions_height': 60.0,
                'creation_year': 999,
                'creator_id': self.creator.id,
            })
            # Flush to trigger constraint
            self.env.flush_all()

        error_msg = str(cm.exception).lower()
        self.assertIn('creation year', error_msg)
        self.assertIn('1000', error_msg)

    def test_creation_year_validation_invalid_too_late(self):
        """Test creation_year validation with year after 2100."""
        # Try to create artwork with year > 2100
        # Constraint is automatically called on create/write
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create({
                'name': 'Future Artwork',
                'product_type': 'artwork',
                'product_subtype': 'painting',
                'dimensions_width': 50.0,
                'dimensions_height': 60.0,
                'creation_year': 2101,
                'creator_id': self.creator.id,
            })
            # Flush to trigger constraint
            self.env.flush_all()

        error_msg = str(cm.exception).lower()
        self.assertIn('creation year', error_msg)
        self.assertIn('2100', error_msg)

    def test_artwork_type_painting(self):
        """Test artwork type painting."""
        artwork = self.ProductTemplate.create({
            'name': 'Test Painting',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        self.assertEqual(artwork.product_type, 'artwork')
        self.assertEqual(artwork.product_subtype, 'painting')

        # Paintings should not have edition_info
        # (edition_info is for sculptures and prints)
        artwork.write({'edition_info': False})
        self.assertFalse(artwork.edition_info)

        # Clean up
        artwork.unlink()

    def test_artwork_type_sculpture(self):
        """Test artwork type sculpture."""
        artwork = self.ProductTemplate.create({
            'name': 'Test Sculpture',
            'product_type': 'artwork',
            'product_subtype': 'sculpture',
            'dimensions_width': 30.0,
            'dimensions_height': 40.0,
            'dimensions_depth': 20.0,
            'creator_id': self.creator.id,
        })

        self.assertEqual(artwork.product_type, 'artwork')
        self.assertEqual(artwork.product_subtype, 'sculpture')

        # Sculptures can have edition_info
        artwork.write({'edition_info': 'Edition 1/10'})
        self.assertEqual(artwork.edition_info, 'Edition 1/10')

        # Clean up
        artwork.unlink()

    def test_dimensions_validation_positive_values(self):
        """Test dimensions validation - positive values only."""
        # Test valid positive dimensions
        artwork = self.ProductTemplate.create({
            'name': 'Valid Dimensions',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        self.assertEqual(artwork.dimensions_width, 50.0)
        self.assertEqual(artwork.dimensions_height, 60.0)

        # Clean up
        artwork.unlink()

    def test_dimensions_validation_negative_width(self):
        """Test dimensions validation - negative width raises error."""
        # Constraint is automatically called on create/write
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create({
                'name': 'Invalid Width',
                'product_type': 'artwork',
                'product_subtype': 'painting',
                'dimensions_width': -10.0,
                'dimensions_height': 60.0,
                'creator_id': self.creator.id,
            })
            # Flush to trigger constraint
            self.env.flush_all()

        error_msg = str(cm.exception).lower()
        self.assertIn('width', error_msg)
        self.assertIn('positive', error_msg)

    def test_dimensions_validation_negative_height(self):
        """Test dimensions validation - negative height raises error."""
        # Constraint is automatically called on create/write
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create({
                'name': 'Invalid Height',
                'product_type': 'artwork',
                'product_subtype': 'painting',
                'dimensions_width': 50.0,
                'dimensions_height': -10.0,
                'creator_id': self.creator.id,
            })
            # Flush to trigger constraint
            self.env.flush_all()

        error_msg = str(cm.exception).lower()
        self.assertIn('height', error_msg)
        self.assertIn('positive', error_msg)

    def test_dimensions_required_for_artwork(self):
        """Test that dimensions are required for artwork type."""
        # Try to create artwork without width
        # Constraint is automatically called on create/write
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create({
                'name': 'No Width',
                'product_type': 'artwork',
                'product_subtype': 'painting',
                # dimensions_width intentionally omitted
                'dimensions_height': 60.0,
                'creator_id': self.creator.id,
            })
            # Flush to trigger constraint
            self.env.flush_all()

        error_msg = str(cm.exception).lower()
        self.assertIn('width', error_msg)
        self.assertIn('required', error_msg)

    def test_depth_required_for_sculpture(self):
        """Test that depth is required for sculptures."""
        # Try to create sculpture without depth
        # The constraint decorator is @api.constrains('dimensions_depth'),
        # so we need to explicitly set dimensions_depth to False to trigger it
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create({
                'name': 'Sculpture No Depth',
                'product_type': 'artwork',
                'product_subtype': 'sculpture',
                'dimensions_width': 30.0,
                'dimensions_height': 40.0,
                'dimensions_depth': False,  # Explicitly set to False to trigger constraint
                'creator_id': self.creator.id,
            })
            # Flush to trigger constraint
            self.env.flush_all()

        error_msg = str(cm.exception).lower()
        self.assertIn('depth', error_msg)
        self.assertIn('required', error_msg)

    def test_certificate_fields(self):
        """Test certificate fields (certificate_of_authenticity, certificate_attachment_ids)."""
        artwork = self.ProductTemplate.create({
            'name': 'Artwork With Certificate',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'certificate_of_authenticity': True,
            'creator_id': self.creator.id,
        })

        # Verify certificate field
        self.assertTrue(artwork.certificate_of_authenticity)

        # Verify certificate_attachment_ids field exists
        self.assertTrue(hasattr(artwork, 'certificate_attachment_ids'))

        # Clean up
        artwork.unlink()

    def test_work_image_ids_one2many(self):
        """Test work_image_ids One2many relationship."""
        artwork = self.ProductTemplate.create({
            'name': 'Artwork With Images',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        # Verify work_image_ids field exists
        self.assertTrue(hasattr(artwork, 'work_image_ids'))
        self.assertEqual(len(artwork.work_image_ids), 0)

        # Verify the relationship model name
        self.assertEqual(artwork.work_image_ids._name, 'sor.art.work.image')

        # Verify inverse field (work_id) exists on image model
        image_model = self.ArtworkImage
        self.assertTrue(hasattr(image_model, '_fields'))
        self.assertIn('work_id', image_model._fields)

        # Verify sequence field exists for ordering
        self.assertIn('sequence', image_model._fields)

        # Note: Creating actual image records requires binary data
        # The relationship structure is tested above

        # Clean up
        artwork.unlink()

    def test_product_type_subtype_validation(self):
        """Test product_type and product_subtype validation."""
        # Test valid combination: artwork + painting
        artwork = self.ProductTemplate.create({
            'name': 'Valid Combination',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        self.assertEqual(artwork.product_type, 'artwork')
        self.assertEqual(artwork.product_subtype, 'painting')

        # Clean up
        artwork.unlink()

    def test_invalid_product_type_subtype_combination(self):
        """Test invalid product_type and product_subtype combination raises error."""
        # Try to create artwork with furniture subtype
        # Constraint is automatically called on create/write
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create({
                'name': 'Invalid Combination',
                'product_type': 'artwork',
                'product_subtype': 'chair',  # Invalid: chair is furniture subtype
                'dimensions_width': 50.0,
                'dimensions_height': 60.0,
                'creator_id': self.creator.id,
            })
            # Flush to trigger constraint
            self.env.flush_all()

        error_msg = str(cm.exception).lower()
        self.assertIn('invalid', error_msg)
        self.assertIn('subtype', error_msg)

    def test_edition_info_not_for_paintings(self):
        """Test that edition_info is not for paintings."""
        artwork = self.ProductTemplate.create({
            'name': 'Painting No Edition',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': self.creator.id,
        })

        # Paintings should not have edition_info
        # The onchange should clear it if set
        artwork.write({'edition_info': 'Test'})
        # Trigger onchange
        artwork._onchange_product_subtype()

        # Edition info should be cleared for paintings
        self.assertFalse(artwork.edition_info)

        # Clean up
        artwork.unlink()

    def test_edition_info_for_sculptures(self):
        """Test that edition_info is allowed for sculptures."""
        artwork = self.ProductTemplate.create({
            'name': 'Sculpture With Edition',
            'product_type': 'artwork',
            'product_subtype': 'sculpture',
            'dimensions_width': 30.0,
            'dimensions_height': 40.0,
            'dimensions_depth': 20.0,
            'edition_info': 'Edition 1/10',
            'creator_id': self.creator.id,
        })

        # Sculptures can have edition_info
        self.assertEqual(artwork.edition_info, 'Edition 1/10')

        # Clean up
        artwork.unlink()
