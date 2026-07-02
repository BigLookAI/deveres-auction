# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import time

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .test_performance_data import PerformanceDataGenerator

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install', 'performance')
class TestPerformance(TransactionCase):
    """Performance tests for sor_artwork module.

    Tests performance with large datasets:
    - List view load time with 1000+ artworks
    - Search performance with filters
    - Computed field performance
    - Relationship query performance
    - Database query optimization
    """

    # Performance thresholds (in seconds)
    LIST_VIEW_THRESHOLD = 2.0  # List view should load in < 2 seconds
    SEARCH_THRESHOLD = 1.0     # Search should complete in < 1 second
    COMPUTED_FIELD_THRESHOLD = 0.5  # Computed fields should be fast

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.generator = PerformanceDataGenerator(cls.env)

        # Create test dataset
        _logger.info("Setting up performance test data...")
        cls.dataset = cls.generator.create_complete_dataset(
            contact_count=1000,
            artwork_count=1000,
            images_per_artwork=3,
        )
        cls.contacts = cls.dataset['contacts']
        cls.artworks = cls.dataset['artworks']
        _logger.info(f"Created {len(cls.contacts)} contacts and {len(cls.artworks)} artworks")

    @mute_logger('odoo.models.unlink', 'odoo.addons.sor_artwork.tests.test_performance_data')
    def test_list_view_performance_large_dataset(self):
        """Test list view load time with 1000+ artworks."""
        # Search for all artworks (simulating list view load)
        start_time = time.time()

        artworks = self.env['product.template'].search([
            ('product_type', '=', 'artwork'),
        ])

        # Read records (simulating what list view does)
        artworks.read(['name', 'product_type', 'product_subtype', 'creation_year',
                      'dimensions_width', 'dimensions_height', 'medium', 'creator_id'])

        elapsed_time = time.time() - start_time

        _logger.info(f"List view load time: {elapsed_time:.3f} seconds for {len(artworks)} records")

        self.assertGreaterEqual(
            len(artworks),
            1000,
            f"Should have at least 1000 artworks, but found {len(artworks)}",
        )
        self.assertLess(
            elapsed_time,
            self.LIST_VIEW_THRESHOLD,
            f"List view should load in < {self.LIST_VIEW_THRESHOLD} seconds, "
            f"but took {elapsed_time:.3f} seconds",
        )

    @mute_logger('odoo.models.unlink', 'odoo.addons.sor_artwork.tests.test_performance_data')
    def test_search_performance_large_dataset(self):
        """Test search performance with filters."""
        # Test search by product_subtype
        start_time = time.time()
        paintings = self.env['product.template'].search([
            ('product_type', '=', 'artwork'),
            ('product_subtype', '=', 'painting'),
        ])
        elapsed_time = time.time() - start_time

        _logger.info(f"Search by subtype time: {elapsed_time:.3f} seconds, found {len(paintings)} paintings")

        self.assertLess(
            elapsed_time,
            self.SEARCH_THRESHOLD,
            f"Search should complete in < {self.SEARCH_THRESHOLD} seconds, "
            f"but took {elapsed_time:.3f} seconds",
        )

        # Test search by creator
        start_time = time.time()
        creator_artworks = self.env['product.template'].search([
            ('product_type', '=', 'artwork'),
            ('creator_id', 'in', self.contacts[:10].ids),
        ])
        elapsed_time = time.time() - start_time

        _logger.info(f"Search by creator time: {elapsed_time:.3f} seconds, found {len(creator_artworks)} artworks")

        self.assertLess(
            elapsed_time,
            self.SEARCH_THRESHOLD,
            f"Search by creator should complete in < {self.SEARCH_THRESHOLD} seconds, "
            f"but took {elapsed_time:.3f} seconds",
        )

        # Test search by creation_year
        start_time = time.time()
        recent_artworks = self.env['product.template'].search([
            ('product_type', '=', 'artwork'),
            ('creation_year', '>=', 2020),
        ])
        elapsed_time = time.time() - start_time

        _logger.info(f"Search by year time: {elapsed_time:.3f} seconds, found {len(recent_artworks)} artworks")

        self.assertLess(
            elapsed_time,
            self.SEARCH_THRESHOLD,
            f"Search by year should complete in < {self.SEARCH_THRESHOLD} seconds, "
            f"but took {elapsed_time:.3f} seconds",
        )

    @mute_logger('odoo.models.unlink', 'odoo.addons.sor_artwork.tests.test_performance_data')
    def test_computed_fields_performance(self):
        """Test computed field performance (no N+1 query issues)."""
        # Test product_subtype_whitelist computed field
        artworks = self.artworks[:100]  # Test with 100 records

        start_time = time.time()
        for artwork in artworks:
            # Access computed field (should not cause N+1 queries)
            _ = artwork.product_subtype_whitelist
        elapsed_time = time.time() - start_time

        _logger.info(f"Computed field access time: {elapsed_time:.3f} seconds for 100 records")

        avg_time_per_record = elapsed_time / len(artworks)
        self.assertLess(
            avg_time_per_record,
            self.COMPUTED_FIELD_THRESHOLD,
            f"Computed field access should be fast (< {self.COMPUTED_FIELD_THRESHOLD}s per record), "
            f"but took {avg_time_per_record:.3f} seconds per record",
        )

    @mute_logger('odoo.models.unlink', 'odoo.addons.sor_artwork.tests.test_performance_data')
    def test_contact_artwork_relationship_performance(self):
        """Test relationship query performance."""
        # Test accessing creator from artwork
        artworks = self.artworks[:100]

        start_time = time.time()
        for artwork in artworks:
            if artwork.creator_id:
                _ = artwork.creator_id.name
        elapsed_time = time.time() - start_time

        _logger.info(f"Relationship access time: {elapsed_time:.3f} seconds for 100 artworks")

        avg_time_per_record = elapsed_time / len(artworks)
        self.assertLess(
            avg_time_per_record,
            self.COMPUTED_FIELD_THRESHOLD,
            f"Relationship access should be fast (< {self.COMPUTED_FIELD_THRESHOLD}s per record), "
            f"but took {avg_time_per_record:.3f} seconds per record",
        )

        # Test reverse relationship (if artwork_ids exists on partner)
        if hasattr(self.contacts[0], 'artwork_ids'):
            start_time = time.time()
            for contact in self.contacts[:50]:
                _ = len(contact.artwork_ids)
            elapsed_time = time.time() - start_time

            _logger.info(f"Reverse relationship access time: {elapsed_time:.3f} seconds for 50 contacts")

            avg_time_per_record = elapsed_time / 50
            self.assertLess(
                avg_time_per_record,
                self.COMPUTED_FIELD_THRESHOLD * 2,  # Allow more time for reverse relationships
                f"Reverse relationship access should be reasonable, "
                f"but took {avg_time_per_record:.3f} seconds per record",
            )

    @mute_logger('odoo.models.unlink', 'odoo.addons.sor_artwork.tests.test_performance_data')
    def test_bulk_create_performance(self):
        """Test bulk creation performance."""
        # Create 100 new artworks
        creator_ids = self.contacts[:10].ids
        artworks_data = []

        for i in range(100):
            artworks_data.append({
                'name': f'Bulk Artwork {i + 1}',
                'product_type': 'artwork',
                'product_subtype': 'painting',
                'dimensions_width': 50.0,
                'dimensions_height': 60.0,
                'medium': 'Oil on canvas',
                'creation_year': 2020,
                'creator_id': creator_ids[i % len(creator_ids)],
            })

        start_time = time.time()
        new_artworks = self.env['product.template'].create(artworks_data)
        elapsed_time = time.time() - start_time

        _logger.info(f"Bulk create time: {elapsed_time:.3f} seconds for 100 artworks")

        avg_time_per_record = elapsed_time / len(new_artworks)
        self.assertLess(
            avg_time_per_record,
            0.1,  # Should be very fast for bulk operations
            f"Bulk create should be fast (< 0.1s per record), "
            f"but took {avg_time_per_record:.3f} seconds per record",
        )

        # Clean up
        new_artworks.unlink()

    @mute_logger('odoo.models.unlink', 'odoo.addons.sor_artwork.tests.test_performance_data')
    def test_query_optimization(self):
        """Verify database queries are optimized (no obvious N+1 issues)."""
        # This is a basic check - in production, you might use assertQueryCount
        # For now, we'll verify that accessing related records doesn't cause excessive queries

        artworks = self.artworks[:50]

        # Access creator for each artwork
        # In optimized code, this should use prefetching
        start_time = time.time()
        creator_names = []
        for artwork in artworks:
            if artwork.creator_id:
                creator_names.append(artwork.creator_id.name)
        elapsed_time = time.time() - start_time

        _logger.info(f"Query optimization test: {elapsed_time:.3f} seconds for 50 artworks")

        # If this takes too long, there might be N+1 query issues
        self.assertLess(
            elapsed_time,
            1.0,  # Should be fast with proper prefetching
            f"Query optimization check: accessing related records should be fast, "
            f"but took {elapsed_time:.3f} seconds. Possible N+1 query issue.",
        )

        self.assertEqual(
            len(creator_names),
            len([a for a in artworks if a.creator_id]),
            "Should have retrieved creator names for all artworks with creators",
        )
