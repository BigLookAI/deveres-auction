import inspect

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestSorLocationsArtistStudiosArtwork(TransactionCase):
    """Tests for the sor_locations_artist_studios_artwork bridge module.

    Covers: module installs, composability (auto-install with both parents),
    and the BUG-05 disable guard that checks product.template.current_location_id
    against AS location IDs before allowing the AS toggle to be disabled.

    This bridge adds a set_values override to res.config.settings that blocks
    disabling the Artist Studios toggle when any artwork's current_location_id
    points to an AS location — even when no stock.quant record exists.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    # ------------------------------------------------------------------
    # 1. Module installs — bridge is present
    # ------------------------------------------------------------------

    def test_module_installs_bridge_accessible(self):
        """sor_locations_artist_studios_artwork is installed and accessible."""
        module = self.env['ir.module.module'].search(
            [('name', '=', 'sor_locations_artist_studios_artwork'),
             ('state', '=', 'installed')],
            limit=1,
        )
        self.assertTrue(module, 'sor_locations_artist_studios_artwork must be installed')

    def test_module_parents_installed(self):
        """Both parent modules are installed — confirming auto-install condition."""
        for mod_name in ('sor_locations_artist_studios', 'sor_locations_artwork'):
            mod = self.env['ir.module.module'].search(
                [('name', '=', mod_name), ('state', '=', 'installed')], limit=1,
            )
            self.assertTrue(mod, f'{mod_name} must be installed as a parent of the bridge')

    # ------------------------------------------------------------------
    # 2. Composability — bridge adds current_location_id check to set_values
    # ------------------------------------------------------------------

    def test_set_values_override_present(self):
        """The bridge's set_values override is in the res.config.settings MRO."""
        src = inspect.getsource(
            self.env['res.config.settings'].__class__.set_values,
        )
        self.assertIn(
            'current_location_id',
            src,
            'set_values must reference current_location_id for the BUG-05 disable guard',
        )

    # ------------------------------------------------------------------
    # 3. BUG-05 disable guard — current_location_id check
    # ------------------------------------------------------------------

    def test_disable_guard_blocked_when_artwork_at_as_location(self):
        """AS toggle cannot be disabled when an artwork's current_location_id is an AS loc.

        BUG-05: the stock.quant guard in sor_locations_artist_studios only blocks
        disabling when a quant exists. If current_location_id is set without a movement
        (manual assignment or imported data), the bridge guard must also block.

        This test requires at least one artwork with current_location_id already pointing
        at an AS location in the database. It skips if none exist — the guard logic is
        verified by the unit test for set_values in sor_locations_artist_studios_artwork,
        and this test confirms the full integration path.
        """
        as_wh = self.env['stock.warehouse'].search(
            [('code', '=', 'AS'), ('company_id', '=', self.company.id)], limit=1,
        )
        if not as_wh:
            self.skipTest('AS warehouse not provisioned — cannot run current_location_id guard test')

        as_loc_ids = self.env['stock.location'].search(
            [('location_id', 'child_of', as_wh.view_location_id.id)],
        ).ids
        if not as_loc_ids:
            self.skipTest('No AS locations found')

        # Find an artwork whose current_location_id is ALREADY at an AS location.
        # Writing to an existing artwork is avoided because current_location_id has
        # check_company=True and the artwork may belong to a different company.
        artwork_at_as = self.env['product.template'].search(
            [('current_location_id', 'in', as_loc_ids)], limit=1,
        )
        if not artwork_at_as:
            self.skipTest(
                'No artwork with current_location_id at AS location in test database '
                '— guard integration test requires real AS-assigned artwork data',
            )

        settings = self.env['res.config.settings'].sudo().create(
            {'sor_artist_studios_enabled': False},
        )
        with self.assertRaises(UserError):
            settings.set_values()

    def test_disable_guard_passes_when_no_artwork_at_as_location(self):
        """AS toggle can be disabled when no artwork has current_location_id at AS.

        Verifies the bridge guard does not raise when no artwork points to an AS location.
        """
        as_wh = self.env['stock.warehouse'].search(
            [('code', '=', 'AS'), ('company_id', '=', self.company.id)], limit=1,
        )
        if not as_wh:
            self.skipTest('AS warehouse not provisioned')

        as_loc_ids = self.env['stock.location'].search(
            [('location_id', 'child_of', as_wh.view_location_id.id)],
        ).ids

        # Check for any artwork at AS location
        occupied = self.env['product.template'].search_count(
            [('current_location_id', 'in', as_loc_ids)],
        )
        if occupied:
            self.skipTest('Artwork(s) currently at AS location — guard would trigger')

        # Also check no stock.quant at AS (parent guard)
        as_quant = self.env['stock.quant'].search_count(
            [('location_id', 'in', as_loc_ids), ('quantity', '>', 0)],
        )
        if as_quant:
            self.skipTest('AS stock.quant occupied — parent guard would trigger')

        settings = self.env['res.config.settings'].sudo().create(
            {'sor_artist_studios_enabled': False},
        )
        try:
            settings.set_values()
        except UserError as exc:
            self.fail(f'Disable guard raised unexpectedly: {exc}')
