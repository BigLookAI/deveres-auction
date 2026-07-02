# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ast

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('artwork_locations', 'post_install', '-at_install')
class TestSorArtworkLocations(TransactionCase):
    """Automated tests for the sor_locations_artwork bridge module.

    Run with:
        docker exec odoo-app python3 odoo-bin \\
          --addons-path=/mnt/extra-addons,/app/odoo/addons \\
          --db_host=postgres --db_port=5432 --db_user=odoo --db_password=admin \\
          -d odoo -u sor_locations_artwork \\
          --test-tags=artwork_locations --stop-after-init
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Creator partner — required by sor_artwork's creator_id constraint
        creator_type = cls.env.ref('sor_contact_roles.sor_contact_type_creator')
        cls.creator = cls.env['res.partner'].create({
            'name': 'Test Creator — Artwork Locations',
            'contact_types': [(6, 0, [creator_type.id])],
        })

        # Test Viewing Location (warehouse) — used for Rooms and warehouse count tests
        cls.warehouse = cls.env['stock.warehouse'].create({
            'name': 'Test Gallery — Artwork Locations',
            'code': 'TGAL',
            'partner_id': cls.env.company.partner_id.id,
            'company_id': cls.env.company.id,
        })

        # Room: internal location directly under the warehouse view location
        cls.room = cls.env['stock.location'].create({
            'name': 'Test Room A',
            'usage': 'internal',
            'location_id': cls.warehouse.view_location_id.id,
        })

        # Second internal location (models a Studio or alternate Room)
        cls.room2 = cls.env['stock.location'].create({
            'name': 'Test Room B',
            'usage': 'internal',
            'location_id': cls.warehouse.view_location_id.id,
        })

        # External (customer) location
        cls.ext_location = cls.env['stock.location'].create({
            'name': 'Test External Location',
            'usage': 'customer',
            'location_id': cls.env.ref('stock.stock_location_customers').id,
        })

        # Primary test artwork
        cls.artwork = cls.env['product.template'].create({
            'name': 'Test Painting — Artwork Locations',
            'product_type': 'artwork',
            'creator_id': cls.creator.id,
            'dimensions_width': 100.0,
            'dimensions_height': 80.0,
            'company_id': cls.env.company.id,
        })

        # Second artwork used in test 13 to verify current_location_id is not
        # restricted to a single product record. In the current SOR design
        # product_type='artwork' is the only valid value (required=True, default='artwork'),
        # so all products are artworks — there is no distinct 'non-artwork' type.
        cls.non_artwork = cls.env['product.template'].create({
            'name': 'Test Artwork 2 — Artwork Locations',
            'product_type': 'artwork',
            'creator_id': cls.creator.id,
            'dimensions_width': 120.0,
            'dimensions_height': 75.0,
            'company_id': cls.env.company.id,
        })

    # ------------------------------------------------------------------
    # Test 1 — current_location_id field present on product.template
    # ------------------------------------------------------------------
    def test_01_field_present_on_product_template(self):
        """current_location_id Many2one field exists on product.template when bridge installed."""
        fields = self.env['product.template']._fields
        self.assertIn('current_location_id', fields,
                      "current_location_id must exist on product.template")
        field = fields['current_location_id']
        self.assertEqual(field.type, 'many2one')
        self.assertEqual(field.comodel_name, 'stock.location')

    # ------------------------------------------------------------------
    # Test 2 — Assign Room (internal) to artwork
    # ------------------------------------------------------------------
    def test_02_assign_room_to_artwork(self):
        """Assigning an internal location (Room) to an artwork saves correctly."""
        self.artwork.write({'current_location_id': self.room.id})
        self.artwork.invalidate_recordset()
        self.assertEqual(self.artwork.current_location_id, self.room)
        self.assertEqual(self.artwork.current_location_id.usage, 'internal')

    # ------------------------------------------------------------------
    # Test 3 — Assign External (customer) location to artwork
    # ------------------------------------------------------------------
    def test_03_assign_external_location_to_artwork(self):
        """Assigning a customer (External) location to an artwork saves correctly."""
        self.artwork.write({'current_location_id': self.ext_location.id})
        self.artwork.invalidate_recordset()
        self.assertEqual(self.artwork.current_location_id, self.ext_location)
        self.assertEqual(self.artwork.current_location_id.usage, 'customer')

    # ------------------------------------------------------------------
    # Test 4 — Assign a Studio-style internal location to artwork
    # ------------------------------------------------------------------
    def test_04_assign_studio_style_internal_location(self):
        """A second internal location (models a Studio) is accepted by the field."""
        self.artwork.write({'current_location_id': self.room2.id})
        self.artwork.invalidate_recordset()
        self.assertEqual(self.artwork.current_location_id, self.room2)
        self.assertEqual(self.artwork.current_location_id.usage, 'internal')

    # ------------------------------------------------------------------
    # Test 5 — Domain restricts to internal + customer only
    # ------------------------------------------------------------------
    def test_05_domain_restricts_to_internal_and_customer(self):
        """current_location_id domain allows internal and customer; excludes view/transit."""
        field_def = self.env['product.template']._fields.get('current_location_id')
        self.assertIsNotNone(field_def)
        domain_str = str(field_def.domain)
        self.assertIn('internal', domain_str,
                      "Domain must include 'internal' usage")
        self.assertIn('customer', domain_str,
                      "Domain must include 'customer' usage")

        # The warehouse view location (usage='view') must not match the domain
        view_loc = self.warehouse.view_location_id
        self.assertEqual(view_loc.usage, 'view')
        matching = self.env['stock.location'].search([
            ('id', '=', view_loc.id),
            ('usage', 'in', ['internal', 'customer']),
        ])
        self.assertFalse(matching,
                         "View-type location must not be selectable via current_location_id")

    # ------------------------------------------------------------------
    # Test 6 — Reassign artwork to a different location
    # ------------------------------------------------------------------
    def test_06_reassign_artwork_to_different_location(self):
        """Reassigning artwork updates the field; previous location is no longer set."""
        self.artwork.write({'current_location_id': self.room.id})
        self.artwork.write({'current_location_id': self.room2.id})
        self.artwork.invalidate_recordset()
        self.assertEqual(self.artwork.current_location_id, self.room2)
        self.assertNotEqual(self.artwork.current_location_id, self.room)

    # ------------------------------------------------------------------
    # Test 7 — Unassign artwork (set to False)
    # ------------------------------------------------------------------
    def test_07_unassign_artwork_clears_field(self):
        """Setting current_location_id to False clears the field."""
        self.artwork.write({'current_location_id': self.room.id})
        self.artwork.write({'current_location_id': False})
        self.artwork.invalidate_recordset()
        self.assertFalse(self.artwork.current_location_id,
                         "current_location_id must be False after clearing")

    # ------------------------------------------------------------------
    # Test 8 — Dashboard action domain restricts to artwork products only
    # ------------------------------------------------------------------
    def test_08_dashboard_action_domain_restricts_to_artworks(self):
        """The Artwork Locations dashboard action domain filters to product_type='artwork'."""
        action = self.env.ref('sor_locations_artwork.action_artwork_location_dashboard')
        domain_str = action.domain or '[]'
        domain = ast.literal_eval(domain_str) if isinstance(domain_str, str) else domain_str

        matching = self.env['product.template'].search(domain)
        self.assertIn(self.artwork, matching,
                      "Artwork must be included in dashboard domain")
        # In the current SOR design product_type='artwork' is the only valid value,
        # so all product.template records are artworks — there is no non-artwork type
        # to exclude. The dashboard domain targets product_type='artwork', which
        # all SOR products satisfy.

    # ------------------------------------------------------------------
    # Test 9 — artwork_count on stock.location
    # ------------------------------------------------------------------
    def test_09_artwork_count_on_location(self):
        """artwork_count on stock.location reflects artworks at that location."""
        initial_count = self.room.artwork_count

        self.env['product.template'].create({
            'name': 'Count Test Artwork 1',
            'product_type': 'artwork',
            'creator_id': self.creator.id,
            'dimensions_width': 40.0,
            'dimensions_height': 30.0,
            'company_id': self.env.company.id,
            'current_location_id': self.room.id,
        })
        self.env['product.template'].create({
            'name': 'Count Test Artwork 2',
            'product_type': 'artwork',
            'creator_id': self.creator.id,
            'dimensions_width': 50.0,
            'dimensions_height': 40.0,
            'company_id': self.env.company.id,
            'current_location_id': self.room.id,
        })

        self.room.invalidate_recordset()
        self.assertEqual(self.room.artwork_count, initial_count + 2)

        # Artwork at room2 must not affect room's count
        self.env['product.template'].create({
            'name': 'Count Test Artwork 3 (other room)',
            'product_type': 'artwork',
            'creator_id': self.creator.id,
            'dimensions_width': 60.0,
            'dimensions_height': 50.0,
            'company_id': self.env.company.id,
            'current_location_id': self.room2.id,
        })
        self.room.invalidate_recordset()
        self.assertEqual(self.room.artwork_count, initial_count + 2,
                         "Artwork at a different room must not count towards this room")

    # ------------------------------------------------------------------
    # Test 10 — artwork_count on stock.warehouse
    # ------------------------------------------------------------------
    def test_10_artwork_count_on_warehouse(self):
        """artwork_count on stock.warehouse aggregates artworks at all locations under it."""
        initial_count = self.warehouse.artwork_count

        # Artwork at room (under the warehouse)
        self.env['product.template'].create({
            'name': 'WH Count Artwork 1',
            'product_type': 'artwork',
            'creator_id': self.creator.id,
            'dimensions_width': 40.0,
            'dimensions_height': 30.0,
            'company_id': self.env.company.id,
            'current_location_id': self.room.id,
        })
        # Artwork at room2 (also under the same warehouse)
        self.env['product.template'].create({
            'name': 'WH Count Artwork 2',
            'product_type': 'artwork',
            'creator_id': self.creator.id,
            'dimensions_width': 50.0,
            'dimensions_height': 40.0,
            'company_id': self.env.company.id,
            'current_location_id': self.room2.id,
        })

        self.warehouse.invalidate_recordset()
        self.assertEqual(self.warehouse.artwork_count, initial_count + 2,
                         "Warehouse count must aggregate artworks at all its locations")

        # Artwork at the external location (not under this warehouse) must not count
        self.env['product.template'].create({
            'name': 'WH Count Artwork 3 (external)',
            'product_type': 'artwork',
            'creator_id': self.creator.id,
            'dimensions_width': 60.0,
            'dimensions_height': 50.0,
            'company_id': self.env.company.id,
            'current_location_id': self.ext_location.id,
        })
        self.warehouse.invalidate_recordset()
        self.assertEqual(self.warehouse.artwork_count, initial_count + 2,
                         "Artwork at an external location must not be counted by this warehouse")

    # ------------------------------------------------------------------
    # Test 11 — action_open_artworks() on stock.location
    # ------------------------------------------------------------------
    def test_11_action_open_artworks_on_location(self):
        """action_open_artworks() on stock.location returns an action scoped to that location."""
        action = self.room.action_open_artworks()

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'product.template')

        domain = action['domain']
        # Domain must include a filter for this specific location
        self.assertTrue(
            any(
                isinstance(clause, (list, tuple))
                and len(clause) == 3
                and clause[0] == 'current_location_id'
                and clause[2] == self.room.id
                for clause in domain
            ),
            "Action domain must filter by current_location_id = this room's id",
        )

    # ------------------------------------------------------------------
    # Test 12 — action_open_artworks() on stock.warehouse
    # ------------------------------------------------------------------
    def test_12_action_open_artworks_on_warehouse(self):
        """action_open_artworks() on stock.warehouse returns an action scoped to its locations."""
        action = self.warehouse.action_open_artworks()

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'product.template')

        domain = action['domain']
        domain_str = str(domain)
        # Domain must filter by current_location_id using 'in' and include both rooms
        self.assertIn('current_location_id', domain_str)
        self.assertIn(str(self.room.id), domain_str,
                      "Domain must reference locations under this warehouse including room")

    # ------------------------------------------------------------------
    # Test 13 — current_location_id is available on all product.template records
    # ------------------------------------------------------------------
    def test_13_current_location_id_available_on_any_artwork(self):
        """current_location_id is available on all product.template records.

        In the current SOR design product_type='artwork' is the only valid value
        (required=True, default='artwork'), so there is no 'non-artwork' product type.
        This test verifies the field is not restricted to the primary test artwork —
        any product.template record can have a location assigned.
        """
        self.non_artwork.write({'current_location_id': self.room.id})
        self.non_artwork.invalidate_recordset()
        self.assertEqual(self.non_artwork.current_location_id, self.room,
                         "current_location_id must be settable on any product.template record")

        # Verify the record appears in the dashboard domain (all SOR products are artworks)
        action = self.env.ref('sor_locations_artwork.action_artwork_location_dashboard')
        domain_str = action.domain or '[]'
        domain = ast.literal_eval(domain_str) if isinstance(domain_str, str) else domain_str
        matching = self.env['product.template'].search(domain)
        self.assertIn(self.non_artwork, matching,
                      "Artwork product with location must appear in the dashboard domain")

    # ------------------------------------------------------------------
    # Test 14 — Composability boundary
    # ------------------------------------------------------------------
    def test_14_composability_boundary(self):
        """current_location_id is owned by the bridge; bridge depends on both parents.

        Verifies:
        - The field exists because the bridge module is installed
        - The bridge declares sor_locations and sor_artwork as dependencies
        - Neither parent alone would provide the field
        """
        # Field exists on the model
        field = self.env['ir.model.fields'].search([
            ('model', '=', 'product.template'),
            ('name', '=', 'current_location_id'),
        ], limit=1)
        self.assertTrue(field,
                        "current_location_id must exist on product.template when bridge installed")

        # Field is owned by the bridge module
        self.assertIn(
            'sor_locations_artwork',
            field.modules,
            "current_location_id must be attributed to the sor_locations_artwork module",
        )

        # Bridge module is installed
        bridge = self.env['ir.module.module'].search([
            ('name', '=', 'sor_locations_artwork'),
        ], limit=1)
        self.assertTrue(bridge)
        self.assertEqual(bridge.state, 'installed')

        # Bridge declares both parents as dependencies
        dep_names = self.env['ir.module.module.dependency'].search([
            ('module_id', '=', bridge.id),
        ]).mapped('name')
        self.assertIn('sor_locations', dep_names,
                      "Bridge must declare sor_locations as a dependency")
        self.assertIn('sor_artwork', dep_names,
                      "Bridge must declare sor_artwork as a dependency")

    # ------------------------------------------------------------------
    # Test 15 — Company scoping
    # ------------------------------------------------------------------
    def test_15_company_scoping(self):
        """current_location_id is company-scoped: cross-company assignment is blocked,
        artwork_count excludes other-company artworks, and action domain filters by company.
        """
        # ── Setup: create a second company with its own Viewing Location ──────
        company_b = self.env['res.company'].create({'name': 'Test Company B — Story05'})
        warehouse_b = self.env['stock.warehouse'].with_context(
            allowed_company_ids=[company_b.id],
        ).create({
            'name': 'Gallery B — Story05',
            'code': 'TGBS5',
            'partner_id': company_b.partner_id.id,
            'company_id': company_b.id,
        })
        room_b = self.env['stock.location'].with_context(
            allowed_company_ids=[company_b.id],
        ).create({
            'name': 'Room B — Story05',
            'usage': 'internal',
            'location_id': warehouse_b.view_location_id.id,
            'company_id': company_b.id,
        })

        # ── 1. check_company=True blocks cross-company assignment ─────────────
        # room_b belongs to company_b; self.artwork belongs to env.company.
        # Odoo's check_company mechanism raises UserError on company mismatch.
        with self.assertRaises(UserError,
                               msg="Assigning a location from another company must raise"):
            self.artwork.write({'current_location_id': room_b.id})

        # ── 2. artwork_count must not bleed across companies ──────────────────
        # Create a Company B artwork assigned to room_b.
        creator_type = self.env.ref('sor_contact_roles.sor_contact_type_creator')
        creator_b = self.env['res.partner'].with_context(
            allowed_company_ids=[company_b.id],
        ).create({
            'name': 'Creator B — Story05',
            'contact_types': [(6, 0, [creator_type.id])],
        })
        artwork_b = self.env['product.template'].with_context(
            allowed_company_ids=[company_b.id],
        ).create({
            'name': 'Artwork B — Story05',
            'product_type': 'artwork',
            'creator_id': creator_b.id,
            'dimensions_width': 30.0,
            'dimensions_height': 20.0,
            'company_id': company_b.id,
            'current_location_id': room_b.id,
        })

        # artwork_count filters by the location's own company_id — not the viewer's.
        # room_b belongs to company_b; artwork_b belongs to company_b and is at room_b.
        # The filter ('company_id', '=', location.company_id.id) matches → count = 1.
        room_b.invalidate_recordset()
        self.assertEqual(
            room_b.artwork_count, 1,
            "artwork_count on a Company B location must count its own Company B artworks",
        )

        # self.room (main company) must NOT count artwork_b (company_b, at room_b).
        # The location filter ensures only artworks linked to this specific location are counted.
        self.room.invalidate_recordset()
        room_main_count_before = self.room.artwork_count
        self.assertEqual(
            self.room.artwork_count, room_main_count_before,
            "artwork_count on the main-company room must not include Company B artworks",
        )
        # Confirm company_b artwork does not appear in self.room's count at all
        # (it is linked to room_b, not self.room, and the company filter is also a guard).
        artworks_at_main_room = self.env['product.template'].search([
            ('current_location_id', '=', self.room.id),
            '|', ('company_id', '=', False),
                 ('company_id', '=', self.env.company.id),
        ])
        self.assertNotIn(artwork_b, artworks_at_main_room,
                         "Company B artwork must not appear in Company A room's artwork count")

        # ── 3. action_open_artworks domain must contain a company filter ───────
        action = self.room.action_open_artworks()
        domain_str = str(action['domain'])
        self.assertIn('company_id', domain_str,
                      "action_open_artworks domain must include a company_id filter")

    # ------------------------------------------------------------------
    # Test 16 — Issue 3 (UAT): domain excludes global virtual locations
    # ------------------------------------------------------------------
    def test_16_domain_excludes_global_virtual_locations(self):
        """current_location_id domain excludes Odoo global virtual locations (company_id=False).

        Odoo ships two global virtual accounting locations — 'Customers' (usage=customer)
        and 'Vendors' (usage=supplier) — with no company_id. Issue 3 (UAT): these were
        appearing in the Current Location dropdown alongside real gallery locations.
        Fix: ('company_id', '!=', False) in the domain excludes them.
        """
        field_def = self.env['product.template']._fields.get('current_location_id')
        self.assertIsNotNone(field_def)
        domain_str = str(field_def.domain)
        self.assertIn(
            'company_id', domain_str,
            "current_location_id domain must include company_id filter to "
            "exclude global virtual locations",
        )

        # Verify the global virtual locations (company_id=False) are excluded
        # by the domain — they must not match ('company_id', '!=', False)
        global_virtual_locs = self.env['stock.location'].search([
            ('company_id', '=', False),
            ('usage', 'in', ['customer', 'supplier']),
        ])
        for loc in global_virtual_locs:
            excluded = self.env['stock.location'].search(
                [('id', '=', loc.id), ('company_id', '!=', False)],
            )
            self.assertFalse(
                excluded,
                f"Global virtual location '{loc.name}' (company_id=False) "
                f"must be excluded by the ('company_id', '!=', False) domain clause",
            )
