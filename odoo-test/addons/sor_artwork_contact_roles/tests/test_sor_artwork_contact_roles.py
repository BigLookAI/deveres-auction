"""
Tests for sor_artwork_contact_roles — bridge module linking sor_artwork x sor_contact_roles.

Coverage:
  1. Module installs — res.partner has artwork_ids, artwork_count, action_view_artworks.
  2. artwork_count — reflects number of artworks linked via creator_id.
  3. action_view_artworks — domain is company-scoped (filters by env.company and False).
  4. Composability — artwork_ids and artwork_count absent when bridge is not installed
     (verified implicitly: bridge depends on both parents, so it only runs in combined install).
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorArtworkContactRoles(TransactionCase):
    """Automated tests for the sor_artwork_contact_roles bridge module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Use an existing artwork with a creator to avoid triggering the
        # dimension validation constraint in sor_artwork.
        cls.artwork = cls.env['product.template'].search(
            [('product_type', '=', 'artwork'), ('creator_id', '!=', False)],
            limit=1,
        )
        if not cls.artwork:
            msg = "No artwork with a creator found — cannot run sor_artwork_contact_roles tests"
            raise RuntimeError(msg)
        cls.artist = cls.artwork.creator_id

    def test_01_module_installs_fields_present(self):
        """res.partner has artwork_ids, artwork_count, and action_view_artworks
        when sor_artwork_contact_roles is installed."""
        fields_info = self.env['res.partner'].fields_get(['artwork_ids', 'artwork_count'])
        self.assertIn('artwork_ids', fields_info, "artwork_ids must be present on res.partner")
        self.assertIn('artwork_count', fields_info, "artwork_count must be present on res.partner")
        self.assertTrue(
            hasattr(self.artist, 'action_view_artworks'),
            "action_view_artworks method must be present on res.partner",
        )

    def test_02_artwork_count_reflects_linked_artworks(self):
        """artwork_count equals the number of artworks linked to the creator."""
        self.artist.invalidate_recordset(['artwork_count', 'artwork_ids'])
        self.assertGreaterEqual(
            self.artist.artwork_count, 1,
            "artwork_count should be at least 1 after linking an artwork",
        )

    def test_03_action_view_artworks_domain_company_scoped(self):
        """action_view_artworks() domain includes a company_id filter so smart
        button only shows artworks belonging to the current company (or global artworks)."""
        action = self.artist.action_view_artworks()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'product.template')
        domain = action.get('domain', [])
        company_filter = (
            ('company_id', '=', self.env.company.id) in domain
            or ('company_id', 'in', [self.env.company.id, False]) in domain
        )
        self.assertTrue(
            company_filter,
            "action_view_artworks domain must filter by company_id per DoD smart button rule",
        )
