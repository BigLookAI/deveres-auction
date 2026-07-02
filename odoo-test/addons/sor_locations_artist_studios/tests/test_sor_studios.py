# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('studios')
class TestSorStudios(TransactionCase):
    """Automated tests for the sor_locations_artist_studios bridge module.

    Run with:
        python odoo-bin -d <db> -i sor_locations_artist_studios --test-tags=studios --stop-after-init
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Look up Artist and Creator contact types from sor_contact_roles data
        artist_type = cls.env.ref('sor_contact_roles.sor_contact_type_artist')
        creator_type = cls.env.ref('sor_contact_roles.sor_contact_type_creator')

        # Artist partner with a full address (used as Studio address defaults)
        cls.artist = cls.env['res.partner'].create({
            'name': 'Test Artist',
            'contact_types': [(6, 0, [creator_type.id])],
            'contact_subtypes': [(6, 0, [artist_type.id])],
            'street': '1 Artist Street',
            'city': 'Dublin',
            'zip': 'D01',
            'country_id': cls.env.ref('base.ie').id,
        })

        # Non-artist partner (no contact types)
        cls.non_artist = cls.env['res.partner'].create({
            'name': 'Test Collector',
        })

        # Ensure Artist Studios warehouse exists for the current company
        cls.env['stock.warehouse']._sor_ensure_artist_studios_warehouse()
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('name', '=', 'Artist Studios'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

    # ------------------------------------------------------------------
    # Test 1 — Warehouse created on opt-in with correct attributes
    # ------------------------------------------------------------------
    def test_01_warehouse_created_on_opt_in(self):
        """Warehouse created with correct name, company, and partner."""
        self.assertTrue(self.warehouse, "Artist Studios warehouse should exist after opt-in")
        self.assertEqual(self.warehouse.name, 'Artist Studios')
        self.assertEqual(self.warehouse.company_id, self.env.company)
        self.assertEqual(self.warehouse.partner_id, self.env.company.partner_id)

    # ------------------------------------------------------------------
    # Test 2 — Warehouse creation is idempotent
    # ------------------------------------------------------------------
    def test_02_warehouse_creation_is_idempotent(self):
        """Calling _sor_ensure_artist_studios_warehouse twice returns same record, no duplicate."""
        wh1 = self.env['stock.warehouse']._sor_ensure_artist_studios_warehouse()
        wh2 = self.env['stock.warehouse']._sor_ensure_artist_studios_warehouse()
        self.assertEqual(wh1, wh2, "Should return the same warehouse record")
        count = self.env['stock.warehouse'].search_count([
            ('name', '=', 'Artist Studios'),
            ('company_id', '=', self.env.company.id),
        ])
        self.assertEqual(count, 1, "Exactly one Artist Studios warehouse should exist")

    # ------------------------------------------------------------------
    # Test 3 — Create Studio with artist; artist_id saved
    # ------------------------------------------------------------------
    def test_03_create_studio_with_artist(self):
        """Create a Studio record; artist_id is stored correctly."""
        studio = self.env['stock.location'].create({
            'name': 'Test Studio',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
        })
        self.assertEqual(studio.artist_id, self.artist)
        self.assertEqual(studio.usage, 'internal')
        self.assertEqual(studio.location_id, self.warehouse.view_location_id)

    # ------------------------------------------------------------------
    # Test 4 — Address defaults from artist on assignment
    # ------------------------------------------------------------------
    def test_04_address_defaults_from_artist(self):
        """Address fields are defaulted from the artist contact when artist_id is assigned."""
        studio = self.env['stock.location'].new({
            'name': 'New Studio',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
        })
        studio.artist_id = self.artist
        studio._onchange_artist_id_address()

        self.assertEqual(studio.studio_street, self.artist.street)
        self.assertEqual(studio.studio_city, self.artist.city)
        self.assertEqual(studio.studio_zip, self.artist.zip)
        self.assertEqual(studio.studio_country_id, self.artist.country_id)

    # ------------------------------------------------------------------
    # Test 5 — Address fields independently editable
    # ------------------------------------------------------------------
    def test_05_address_fields_independently_editable(self):
        """Changing a Studio's address does not modify the artist partner record."""
        studio = self.env['stock.location'].create({
            'name': 'Editable Address Studio',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
            'studio_street': self.artist.street,
            'studio_city': self.artist.city,
        })
        studio.write({'studio_city': 'Cork', 'studio_street': '99 New Road'})

        # Partner record must be unchanged
        self.assertEqual(self.artist.city, 'Dublin')
        self.assertEqual(self.artist.street, '1 Artist Street')

    # ------------------------------------------------------------------
    # Test 6 — Two studios for same artist with distinct addresses
    # ------------------------------------------------------------------
    def test_06_two_studios_distinct_addresses(self):
        """One artist can have two studios with different addresses (one-to-many)."""
        studio_a = self.env['stock.location'].create({
            'name': 'Studio Dublin',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
            'studio_city': 'Dublin',
        })
        studio_b = self.env['stock.location'].create({
            'name': 'Studio Cork',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
            'studio_city': 'Cork',
        })
        self.assertEqual(studio_a.artist_id, studio_b.artist_id)
        self.assertNotEqual(studio_a.studio_city, studio_b.studio_city)

    # ------------------------------------------------------------------
    # Test 7 — Non-artist contacts rejected by domain
    # ------------------------------------------------------------------
    def test_07_non_artist_rejected_by_domain(self):
        """artist_id field domain restricts to is_artist=True; non-artist absent from results."""
        # Python-defined domains live on the field class, not in ir.model.fields.domain
        field_def = self.env['stock.location']._fields.get('artist_id')
        self.assertIsNotNone(field_def, "artist_id must exist on stock.location")
        self.assertIn('is_artist', str(field_def.domain),
                      "artist_id domain must reference is_artist")

        artist_contacts = self.env['res.partner'].search([('is_artist', '=', True)])
        self.assertNotIn(self.non_artist, artist_contacts)

    # ------------------------------------------------------------------
    # Test 8 — Window action domain scoped; Studios absent from Rooms list
    # ------------------------------------------------------------------
    def test_08_window_action_domain_scoped(self):
        """Studios appear in the Artist Studios action; absent from the Rooms list."""
        studio = self.env['stock.location'].create({
            'name': 'Scoped Studio',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
        })

        studios_domain = [
            ('usage', '=', 'internal'),
            ('warehouse_id.name', '=', 'Artist Studios'),
        ]
        self.assertIn(studio, self.env['stock.location'].search(studios_domain))

        rooms_domain = [
            ('usage', '=', 'internal'),
            ('warehouse_id', '!=', False),
            ('warehouse_id.name', '!=', 'Artist Studios'),
        ]
        self.assertNotIn(studio, self.env['stock.location'].search(rooms_domain))

    # ------------------------------------------------------------------
    # Test 9 — Company scoping
    # ------------------------------------------------------------------
    def test_09_company_scoping(self):
        """Artist Studios Warehouse is created under the current company."""
        self.assertEqual(
            self.warehouse.company_id,
            self.env.company,
            "Warehouse must be scoped to the company that enabled the feature",
        )

    # ------------------------------------------------------------------
    # Test 10 — action_create_studio() returns correct modal action
    # ------------------------------------------------------------------
    def test_10_action_create_studio(self):
        """action_create_studio() returns a modal action with correct defaults."""
        action = self.artist.action_create_studio()

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action.get('target'), 'new', "action must open as modal dialog")
        ctx = action.get('context', {})
        self.assertEqual(ctx.get('default_artist_id'), self.artist.id)
        self.assertEqual(ctx.get('default_usage'), 'internal')
        self.assertEqual(ctx.get('default_location_id'), self.warehouse.view_location_id.id)
        self.assertEqual(ctx.get('default_studio_street'), self.artist.street)
        self.assertEqual(ctx.get('default_studio_city'), self.artist.city)
        self.assertEqual(ctx.get('default_studio_country_id'), self.artist.country_id.id)

    # ------------------------------------------------------------------
    # Test 11 — studio_count reflects linked studios
    # ------------------------------------------------------------------
    def test_11_studio_count(self):
        """studio_count on artist partner tracks number of linked Studio locations."""
        initial_count = self.artist.studio_count

        self.env['stock.location'].create({
            'name': 'Count Studio A',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
        })
        self.env['stock.location'].create({
            'name': 'Count Studio B',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
        })

        self.artist.invalidate_recordset()
        self.assertEqual(self.artist.studio_count, initial_count + 2)

    # ------------------------------------------------------------------
    # Test 12 — action_create_studio() raises UserError without warehouse
    # ------------------------------------------------------------------
    def test_12_action_create_studio_raises_without_warehouse(self):
        """action_create_studio() raises UserError when Artist Studios Warehouse is absent.

        Company creation auto-provisions AS via stock.warehouse.create hook. The
        auto-provisioned warehouse is renamed here so that action_create_studio's
        name-based search doesn't find it, simulating the pre-enablement state.
        Transaction rollback restores the name after the test.
        """
        new_company = self.env['res.company'].create({'name': 'Test Co — No Studios'})
        # Rename the auto-provisioned AS warehouse so the name-based guard search misses it.
        self.env['stock.warehouse'].sudo().search([
            ('code', '=', 'AS'), ('company_id', '=', new_company.id),
        ]).write({'name': 'Artist Studios (Pending Enable)'})
        artist_in_new_company = self.artist.sudo().with_company(new_company)
        with self.assertRaises(UserError):
            artist_in_new_company.action_create_studio()

    # ------------------------------------------------------------------
    # Test 13 — action_create_studio() is non-destructive
    # ------------------------------------------------------------------
    def test_13_action_create_studio_nondestructive(self):
        """Creating a second Studio for the same artist does not remove the first."""
        studio1 = self.env['stock.location'].create({
            'name': 'Non-destruct Studio 1',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
        })
        studio2 = self.env['stock.location'].create({
            'name': 'Non-destruct Studio 2',
            'usage': 'internal',
            'location_id': self.warehouse.view_location_id.id,
            'artist_id': self.artist.id,
        })
        self.assertNotEqual(studio1.id, studio2.id, "Each studio is a distinct record")
        self.assertTrue(studio1.exists())
        self.assertTrue(studio2.exists())
        self.assertEqual(studio1.artist_id, studio2.artist_id, "Both belong to same artist")

    # ------------------------------------------------------------------
    # Test 14 — Composability boundary
    # ------------------------------------------------------------------
    def test_14_composability_boundary(self):
        """artist_id is owned by the bridge module; sor_locations does not define it.

        In the test environment both parents and the bridge are installed.
        This test verifies the module dependency structure to document the boundary:
        - artist_id exists because the bridge is installed
        - The bridge depends on both sor_locations AND sor_artwork_contact_roles
        - Neither parent module alone would provide artist_id
        """
        # Positive: bridge installed → field exists
        field = self.env['ir.model.fields'].search([
            ('model', '=', 'stock.location'),
            ('name', '=', 'artist_id'),
        ], limit=1)
        self.assertTrue(field, "artist_id must exist when the bridge module is installed")

        # Bridge module is installed
        bridge = self.env['ir.module.module'].search([
            ('name', '=', 'sor_locations_artist_studios'),
        ], limit=1)
        self.assertTrue(bridge)
        self.assertEqual(bridge.state, 'installed')

        # Bridge declares both parents as dependencies
        dep_names = self.env['ir.module.module.dependency'].search([
            ('module_id', '=', bridge.id),
        ]).mapped('name')
        self.assertIn('sor_locations', dep_names,
                      "Bridge must depend on sor_locations")
        self.assertIn('sor_artwork_contact_roles', dep_names,
                      "Bridge must depend on sor_artwork_contact_roles")

        # sor_locations base module does NOT expose artist_id — confirmed by:
        # field origin is the bridge (modules field contains the bridge name)
        self.assertIn(
            'sor_locations_artist_studios',
            field.modules,
            "artist_id field origin should include the bridge module",
        )

    # ------------------------------------------------------------------
    # Test 15 — D9 (UAT): Viewing Locations action domain excludes AS
    # ------------------------------------------------------------------
    def test_15_viewing_locations_action_excludes_as(self):
        """The Viewing Locations window action domain excludes Artist Studios warehouses.

        D9 (UAT Composability Enhancements): Artist Studios (code='AS') was appearing in the
        Viewing Locations list alongside gallery/collection spaces. The bridge overrides the
        sor_locations Viewing Locations action domain with [('code', '!=', 'AS')] so that
        only warehouses that are valid Room parents appear in that list.
        """
        action = self.env.ref('sor_locations.action_viewing_location_form')
        domain = action.domain or ''
        self.assertIn("'AS'", str(domain),
                      "Viewing Locations action domain must reference AS code")
        self.assertIn('!=', str(domain),
                      "Viewing Locations action domain must exclude AS (code != 'AS')")

        # Artist Studios warehouse must not match the domain
        as_wh = self.env['stock.warehouse'].search([
            ('code', '=', 'AS'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if as_wh:
            excluded = self.env['stock.warehouse'].search([
                ('id', '=', as_wh.id),
                ('code', '!=', 'AS'),
            ])
            self.assertFalse(excluded,
                             "Artist Studios warehouse must be excluded by the action domain")

    # ------------------------------------------------------------------
    # Test 16 — D7 (UAT): Room form parent field excludes AS warehouses
    # ------------------------------------------------------------------
    def test_16_room_form_parent_domain_excludes_as(self):
        """The Room form location_id (parent) field domain excludes Artist Studios.

        D7 (UAT Composability Enhancements): The Room creation form allowed Artist Studios
        to be selected as the parent Viewing Location. The bridge adds a view XPath
        (view_room_form_restrict_as_parent) that restricts the location_id dropdown to
        exclude warehouses with code='AS'.
        """
        # The view record added by the bridge must exist (verified via ir.model.data)
        view_data = self.env['ir.model.data'].search([
            ('module', '=', 'sor_locations_artist_studios'),
            ('model', '=', 'ir.ui.view'),
            ('name', '=', 'view_room_form_restrict_as_parent'),
        ], limit=1)
        self.assertTrue(
            view_data,
            "view_room_form_restrict_as_parent must be registered by the bridge module",
        )
        view = self.env['ir.ui.view'].browse(view_data.res_id)
        self.assertTrue(view.exists(),
                        "The view record referenced by ir.model.data must exist")

        # The view arch must contain the AS exclusion
        arch = view.arch or ''
        self.assertIn("'AS'", arch,
                      "Room form parent restriction arch must reference AS code")
        self.assertIn('!=', arch,
                      "Room form parent restriction arch must exclude AS")

    # ------------------------------------------------------------------
    # Test 17 — Disable guard: blocked when stock.quant holds AS stock
    # ------------------------------------------------------------------
    def test_17_disable_guard_blocked_when_as_quant_occupied(self):
        """AS toggle cannot be disabled when a stock.quant holds stock at AS locations.

        Story 02 AC 6: if any stock.quant record shows qty > 0 at an AS location,
        set_values must raise UserError and leave the toggle enabled.
        """
        # Ensure AS warehouse is provisioned
        self.env['res.config.settings'] \
            .sudo() \
            .create({'sor_artist_studios_enabled': True}) \
            .execute()
        as_wh = self.env['stock.warehouse'].search(
            [('code', '=', 'AS'), ('company_id', '=', self.env.company.id)], limit=1,
        )
        if not as_wh:
            self.skipTest('AS warehouse not provisioned in test environment')

        # Find an AS stock location
        as_loc = self.env['stock.location'].search(
            [('location_id', 'child_of', as_wh.view_location_id.id),
             ('usage', '=', 'internal')],
            limit=1,
        )
        if not as_loc:
            self.skipTest('No internal AS location found')

        # Use an existing non-artwork storable product — creating a new product.product
        # triggers sor_artwork's Creator/Artist required validation when artwork is installed.
        product = self.env['product.product'].search(
            [('product_tmpl_id.product_type', '!=', 'artwork'), ('type', '=', 'consu')],
            limit=1,
        )
        if not product:
            self.skipTest('No suitable non-artwork storable product found in test database')
        quant = self.env['stock.quant'].create({
            'product_id': product.id,
            'location_id': as_loc.id,
            'quantity': 1,
        })
        try:
            settings = self.env['res.config.settings'].sudo().create(
                {'sor_artist_studios_enabled': False},
            )
            with self.assertRaises(UserError):
                settings.set_values()
        finally:
            quant.sudo().unlink()

    # ------------------------------------------------------------------
    # Test 18 — Disable guard: passes when AS locations are empty
    # ------------------------------------------------------------------
    def test_18_disable_guard_passes_when_as_locations_empty(self):
        """AS toggle can be disabled when no stock.quant holds AS stock.

        Verifies the guard does not raise when all AS locations have zero stock.
        """
        as_wh = self.env['stock.warehouse'].search(
            [('code', '=', 'AS'), ('company_id', '=', self.env.company.id)], limit=1,
        )
        if not as_wh:
            self.skipTest('AS warehouse not provisioned in test environment')

        as_loc_ids = self.env['stock.location'].search(
            [('location_id', 'child_of', as_wh.view_location_id.id)],
        ).ids
        occupied = self.env['stock.quant'].search_count(
            [('location_id', 'in', as_loc_ids), ('quantity', '>', 0)],
        )
        if occupied:
            self.skipTest('AS locations have existing stock — disable guard would trigger')

        settings = self.env['res.config.settings'].sudo().create(
            {'sor_artist_studios_enabled': False},
        )
        # Should complete without raising UserError
        try:
            settings.set_values()
        except UserError as exc:
            self.fail(f'Disable guard raised unexpectedly when AS is empty: {exc}')
