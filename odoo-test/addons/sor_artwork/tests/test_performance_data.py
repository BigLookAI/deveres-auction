# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""Helper functions for generating large datasets for performance testing."""


class PerformanceDataGenerator:
    """Helper class to generate large datasets for performance testing."""

    def __init__(self, env):
        self.env = env
        self.Partner = env['res.partner']
        self.ProductTemplate = env['product.template']
        self.ArtworkImage = env['sor.art.work.image']

    def create_large_contact_set(self, count=1000):
        """Create a large set of plain partner contacts.

        Note: Creator type classification (is_creator) is a sor_contact_roles concern.
        In sor_artwork alone, creator_id accepts any partner. Performance tests use plain
        partners as creators to avoid a sor_contact_roles dependency.

        Args:
            count (int): Number of contacts to create (default: 1000)

        Returns:
            recordset: Created contacts
        """
        contacts_data = []
        for i in range(count):
            contacts_data.append({
                'name': f'Artist {i + 1}',
                'email': f'artist{i + 1}@example.com',
            })

        # Create in batches to avoid memory issues
        batch_size = 100
        contacts = self.env['res.partner']

        for i in range(0, count, batch_size):
            batch = contacts_data[i:i + batch_size]
            created = self.Partner.create(batch)
            contacts |= created

        # Assign Creator type if sor_artwork_contact_roles constraint is active
        ContactType = self.env.get('sor.contact.type')
        if ContactType is not None:
            creator_type = ContactType.search([('code', '=', 'creator')], limit=1)
            if creator_type:
                contacts.write({'contact_types': [(4, creator_type.id)]})

        return contacts

    def create_large_artwork_set(self, count=1000, creator_ids=None):
        """Create a large set of artworks.

        Args:
            count (int): Number of artworks to create (default: 1000)
            creator_ids (list): List of creator IDs to assign (if None, creates new creators)

        Returns:
            recordset: Created artworks
        """
        # If no creators provided, create them
        if creator_ids is None:
            creators = self.create_large_contact_set(count=min(count, 100))
            creator_ids = creators.ids

        # Distribute artworks across creators
        artworks_data = []
        artwork_types = ['painting', 'sculpture', 'print']
        mediums = ['Oil on canvas', 'Acrylic', 'Watercolor', 'Bronze', 'Marble', 'Wood', 'Digital print', 'Lithograph']

        for i in range(count):
            artwork_type = artwork_types[i % len(artwork_types)]
            creator_id = creator_ids[i % len(creator_ids)]

            artwork_data = {
                'name': f'Artwork {i + 1}',
                'product_type': 'artwork',
                'product_subtype': artwork_type,
                'dimensions_width': 50.0 + (i % 100),
                'dimensions_height': 60.0 + (i % 100),
                'medium': mediums[i % len(mediums)],
                'creation_year': 2000 + (i % 25),
                'creator_id': creator_id,
            }

            # Add depth for sculptures
            if artwork_type == 'sculpture':
                artwork_data['dimensions_depth'] = 20.0 + (i % 50)
                artwork_data['edition_info'] = f'Edition {i + 1}/10'
            elif artwork_type == 'print':
                artwork_data['edition_info'] = f'Edition {i + 1}/100'

            artworks_data.append(artwork_data)

        # Create in batches
        batch_size = 100
        artworks = self.env['product.template']

        for i in range(0, count, batch_size):
            batch = artworks_data[i:i + batch_size]
            created = self.ProductTemplate.create(batch)
            artworks |= created

        return artworks

    def create_artwork_with_images(self, artwork, image_count=5):
        """Add multiple images to an artwork.

        Args:
            artwork: Artwork record
            image_count (int): Number of images to create (default: 5)

        Returns:
            recordset: Created image records
        """
        # Create dummy image data (1x1 pixel PNG) - base64 encoded
        # Odoo Binary fields expect base64-encoded strings
        import base64  # noqa: PLC0415
        # Minimal 1x1 pixel PNG image
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
        dummy_image = base64.b64encode(png_data).decode('ascii')

        images_data = []
        for i in range(image_count):
            images_data.append({
                'work_id': artwork.id,
                'name': f'Image {i + 1}',
                'image': dummy_image,
                'sequence': (i + 1) * 10,
            })

        return self.ArtworkImage.create(images_data)

    def create_complete_dataset(self, contact_count=1000, artwork_count=1000, images_per_artwork=3):
        """Create a complete dataset for performance testing.

        Args:
            contact_count (int): Number of contacts to create
            artwork_count (int): Number of artworks to create
            images_per_artwork (int): Number of images per artwork

        Returns:
            dict: Dictionary with 'contacts' and 'artworks' recordsets
        """
        print(f"Creating {contact_count} contacts...")
        contacts = self.create_large_contact_set(contact_count)

        print(f"Creating {artwork_count} artworks...")
        artworks = self.create_large_artwork_set(artwork_count, creator_ids=contacts.ids)

        if images_per_artwork > 0:
            print(f"Adding {images_per_artwork} images per artwork...")
            # Add images to a sample of artworks (to avoid too many images)
            sample_size = min(artwork_count, 100)  # Limit to 100 artworks with images
            for artwork in artworks[:sample_size]:
                self.create_artwork_with_images(artwork, image_count=images_per_artwork)

        return {
            'contacts': contacts,
            'artworks': artworks,
        }
