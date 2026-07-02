# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWorkflowIntegration(TransactionCase):
    """Integration tests for complete workflows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']
        cls.ProductTemplate = cls.env['product.template']

        # Get contact types
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

    def test_workflow_create_contact_assign_creator_create_painting_link_creator(self):
        """Test complete workflow: Create contact → Assign Creator type → Create painting → Link creator → Verify relationship."""
        # Step 1: Create contact
        contact = self.Partner.create({
            'name': 'New Artist',
        })

        # Verify contact created
        self.assertTrue(contact.exists())
        self.assertFalse(contact.is_creator)

        # Step 2: Assign Creator type
        contact.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Verify Creator type assigned
        self.assertIn(self.creator_type, contact.contact_types)
        self.assertTrue(contact.is_creator)

        # Step 3: Create painting
        painting = self.ProductTemplate.create({
            'name': 'New Painting',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'medium': 'Oil on canvas',
            'creation_year': 2020,
            'creator_id': contact.id,
        })

        # Verify painting created
        self.assertTrue(painting.exists())
        self.assertEqual(painting.product_type, 'artwork')
        self.assertEqual(painting.product_subtype, 'painting')

        # Step 4: Verify relationship
        self.assertEqual(painting.creator_id, contact)
        self.assertTrue(painting.creator_id.is_creator)

        # Step 5: Verify reverse relationship (if artwork_ids exists)
        if hasattr(contact, 'artwork_ids'):
            self.assertIn(painting, contact.artwork_ids)

        # Clean up
        painting.unlink()
        contact.unlink()

    def test_workflow_create_contact_assign_multiple_types_verify_fields(self):
        """Test workflow: Create contact → Assign multiple types → Verify all fields visible."""
        # Step 1: Create contact
        contact = self.Partner.create({
            'name': 'Multi-Type Contact',
        })

        # Verify no types initially
        self.assertFalse(contact.has_creator_type)
        self.assertFalse(contact.has_customer_type)

        # Step 2: Assign multiple types (Creator + Customer)
        contact.write({
            'contact_types': [
                Command.link(self.creator_type.id),
                Command.link(self.customer_type.id),
            ],
        })

        # Step 3: Verify all type flags are True
        self.assertTrue(contact.has_creator_type)
        self.assertTrue(contact.has_customer_type)
        self.assertTrue(contact.is_creator)
        self.assertTrue(contact.is_customer)

        # Step 4: Verify all relevant fields are accessible
        contact.write({
            'biography': 'Creator biography',
            'collection_focus': 'Customer collection focus',
        })

        self.assertEqual(contact.biography, 'Creator biography')
        self.assertEqual(contact.collection_focus, 'Customer collection focus')

        # Clean up
        contact.unlink()

    def test_workflow_create_painting_assign_creator_verify_artwork_ids(self):
        """Test workflow: Create painting → Assign creator → Verify creator.artwork_ids updated."""
        # Step 1: Create creator
        creator = self.Partner.create({
            'name': 'Test Creator',
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Step 2: Create painting
        painting = self.ProductTemplate.create({
            'name': 'Test Painting',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': creator.id,
        })

        # Step 3: Verify relationship
        self.assertEqual(painting.creator_id, creator)

        # Step 4: Verify creator.artwork_ids updated (if field exists)
        if hasattr(creator, 'artwork_ids'):
            self.assertIn(painting, creator.artwork_ids)
            self.assertEqual(len(creator.artwork_ids), 1)

        # Create another painting
        painting2 = self.ProductTemplate.create({
            'name': 'Test Painting 2',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 40.0,
            'dimensions_height': 50.0,
            'creator_id': creator.id,
        })

        # Verify both paintings in artwork_ids
        if hasattr(creator, 'artwork_ids'):
            self.assertIn(painting, creator.artwork_ids)
            self.assertIn(painting2, creator.artwork_ids)
            self.assertEqual(len(creator.artwork_ids), 2)

        # Clean up
        painting.unlink()
        painting2.unlink()
        creator.unlink()

    def test_workflow_create_sculpture_verify_depth_assign_creator(self):
        """Test workflow: Create sculpture → Verify depth required → Assign creator → Verify relationship."""
        # Step 1: Create creator
        creator = self.Partner.create({
            'name': 'Sculptor',
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Step 2: Create sculpture with all required fields
        sculpture = self.ProductTemplate.create({
            'name': 'Test Sculpture',
            'product_type': 'artwork',
            'product_subtype': 'sculpture',
            'dimensions_width': 30.0,
            'dimensions_height': 40.0,
            'dimensions_depth': 20.0,  # Required for sculptures
            'medium': 'Bronze',
            'edition_info': 'Edition 1/10',
            'creator_id': creator.id,
        })

        # Step 3: Verify sculpture created with all fields
        self.assertEqual(sculpture.product_type, 'artwork')
        self.assertEqual(sculpture.product_subtype, 'sculpture')
        self.assertEqual(sculpture.dimensions_depth, 20.0)
        self.assertEqual(sculpture.medium, 'Bronze')
        self.assertEqual(sculpture.edition_info, 'Edition 1/10')

        # Step 4: Verify creator relationship
        self.assertEqual(sculpture.creator_id, creator)

        # Step 5: Verify reverse relationship
        if hasattr(creator, 'artwork_ids'):
            self.assertIn(sculpture, creator.artwork_ids)

        # Clean up
        sculpture.unlink()
        creator.unlink()

    def test_workflow_contact_without_types_normal_behavior(self):
        """Test workflow: Create contact without types → Verify normal res.partner behavior."""
        # Step 1: Create contact without types
        contact = self.Partner.create({
            'name': 'Normal Contact',
            'email': 'normal@example.com',
            'phone': '123-456-7890',
            'street': '123 Main St',
            'city': 'Test City',
            'zip': '12345',
        })

        # Step 2: Verify no contact types
        self.assertFalse(contact.contact_types)
        self.assertFalse(contact.contact_subtypes)

        # Step 3: Verify computed fields are False
        self.assertFalse(contact.is_creator)
        self.assertFalse(contact.is_customer)
        self.assertFalse(contact.has_creator_type)
        self.assertFalse(contact.has_customer_type)

        # Step 4: Verify normal res.partner functionality works
        self.assertEqual(contact.name, 'Normal Contact')
        self.assertEqual(contact.email, 'normal@example.com')
        self.assertEqual(contact.phone, '123-456-7890')
        self.assertEqual(contact.street, '123 Main St')
        self.assertEqual(contact.city, 'Test City')
        self.assertEqual(contact.zip, '12345')

        # Step 5: Verify contact can be updated normally
        contact.write({
            'name': 'Updated Normal Contact',
            'email': 'updated@example.com',
        })
        self.assertEqual(contact.name, 'Updated Normal Contact')
        self.assertEqual(contact.email, 'updated@example.com')

        # Clean up
        contact.unlink()

    def test_workflow_complete_artwork_lifecycle(self):
        """Test complete artwork lifecycle: Create → Update → Link creator → Add images → Verify."""
        # Step 1: Create creator
        creator = self.Partner.create({
            'name': 'Lifecycle Artist',
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Step 2: Create artwork
        artwork = self.ProductTemplate.create({
            'name': 'Lifecycle Artwork',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': creator.id,
        })

        # Step 3: Update artwork
        artwork.write({
            'medium': 'Oil on canvas',
            'creation_year': 2020,
            'condition': 'Excellent',
            'provenance': 'Private collection',
            'certificate_of_authenticity': True,
        })

        # Step 4: Verify all updates
        self.assertEqual(artwork.medium, 'Oil on canvas')
        self.assertEqual(artwork.creation_year, 2020)
        self.assertEqual(artwork.condition, 'Excellent')
        self.assertEqual(artwork.provenance, 'Private collection')
        self.assertTrue(artwork.certificate_of_authenticity)

        # Step 5: Verify creator relationship maintained
        self.assertEqual(artwork.creator_id, creator)

        # Step 6: Verify reverse relationship
        if hasattr(creator, 'artwork_ids'):
            self.assertIn(artwork, creator.artwork_ids)

        # Clean up
        artwork.unlink()
        creator.unlink()

    def test_workflow_multiple_artworks_multiple_creators(self):
        """Test workflow with multiple artworks and multiple creators."""
        # Step 1: Create multiple creators
        creator1 = self.Partner.create({
            'name': 'Artist One',
            'contact_types': [Command.link(self.creator_type.id)],
        })
        creator2 = self.Partner.create({
            'name': 'Artist Two',
            'contact_types': [Command.link(self.creator_type.id)],
        })

        # Step 2: Create artworks for each creator
        artwork1 = self.ProductTemplate.create({
            'name': 'Artwork by Artist One',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 50.0,
            'dimensions_height': 60.0,
            'creator_id': creator1.id,
        })

        artwork2 = self.ProductTemplate.create({
            'name': 'Artwork by Artist Two',
            'product_type': 'artwork',
            'product_subtype': 'painting',
            'dimensions_width': 40.0,
            'dimensions_height': 50.0,
            'creator_id': creator2.id,
        })

        artwork3 = self.ProductTemplate.create({
            'name': 'Another Artwork by Artist One',
            'product_type': 'artwork',
            'product_subtype': 'sculpture',
            'dimensions_width': 30.0,
            'dimensions_height': 40.0,
            'dimensions_depth': 20.0,
            'creator_id': creator1.id,
        })

        # Step 3: Verify relationships
        self.assertEqual(artwork1.creator_id, creator1)
        self.assertEqual(artwork2.creator_id, creator2)
        self.assertEqual(artwork3.creator_id, creator1)

        # Step 4: Verify reverse relationships
        if hasattr(creator1, 'artwork_ids'):
            self.assertIn(artwork1, creator1.artwork_ids)
            self.assertIn(artwork3, creator1.artwork_ids)
            self.assertEqual(len(creator1.artwork_ids), 2)

        if hasattr(creator2, 'artwork_ids'):
            self.assertIn(artwork2, creator2.artwork_ids)
            self.assertEqual(len(creator2.artwork_ids), 1)

        # Clean up
        artwork1.unlink()
        artwork2.unlink()
        artwork3.unlink()
        creator1.unlink()
        creator2.unlink()
