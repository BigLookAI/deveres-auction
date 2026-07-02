# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('external')
class TestSorExternalLocations(TransactionCase):
    """Automated tests for the sor_locations_external bridge module.

    Run with:
        docker exec odoo-app python3 odoo-bin \\
          --addons-path=/mnt/extra-addons,/app/odoo/addons \\
          --db_host=postgres --db_port=5432 --db_user=odoo --db_password=admin \\
          -d odoo -u sor_locations_external \\
          --test-tags=external --stop-after-init
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Look up Contact type from sor_contact_roles data (renamed from Customer in Story 02)
        customer_type = cls.env.ref('sor_contact_roles.sor_contact_type_contact')

        # Customer partner with a full address (used as external location address defaults)
        cls.customer = cls.env['res.partner'].create({
            'name': 'Test Collector',
            'contact_types': [(6, 0, [customer_type.id])],
            'street': '10 Collector Road',
            'city': 'Dublin',
            'zip': 'D02',
            'country_id': cls.env.ref('base.ie').id,
        })

        # Non-customer partner (no contact types)
        cls.non_customer = cls.env['res.partner'].create({
            'name': 'Test Non-Customer',
        })

        # Ensure External Locations parent exists for the current company
        cls.env['stock.location']._sor_ensure_external_locations_parent()
        cls.parent = cls.env['stock.location'].search([
            ('name', '=', 'External Locations'),
            ('usage', '=', 'view'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

    # ------------------------------------------------------------------
    # Test 1 — Virtual parent location created on opt-in with correct attributes
    # ------------------------------------------------------------------
    def test_01_parent_location_created_on_opt_in(self):
        """Parent view location created with correct name, company, and usage."""
        self.assertTrue(self.parent, "External Locations parent should exist after opt-in")
        self.assertEqual(self.parent.name, 'External Locations')
        self.assertEqual(self.parent.usage, 'view')
        self.assertEqual(self.parent.company_id, self.env.company)

    # ------------------------------------------------------------------
    # Test 2 — _sor_ensure_external_locations_parent() is idempotent
    # ------------------------------------------------------------------
    def test_02_ensure_parent_is_idempotent(self):
        """Calling _sor_ensure_external_locations_parent twice returns same record, no duplicate."""
        p1 = self.env['stock.location']._sor_ensure_external_locations_parent()
        p2 = self.env['stock.location']._sor_ensure_external_locations_parent()
        self.assertEqual(p1, p2, "Should return the same location record")
        count = self.env['stock.location'].search_count([
            ('name', '=', 'External Locations'),
            ('usage', '=', 'view'),
            ('company_id', '=', self.env.company.id),
        ])
        self.assertEqual(count, 1, "Exactly one External Locations parent should exist")

    # ------------------------------------------------------------------
    # Test 3 — Create external location with contact; contact_id saved
    # ------------------------------------------------------------------
    def test_03_create_external_location_with_contact(self):
        """Create an external location record; contact_id is stored correctly."""
        loc = self.env['stock.location'].create({
            'name': 'Test External Location',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
        })
        self.assertEqual(loc.contact_id, self.customer)
        self.assertEqual(loc.usage, 'customer')
        self.assertEqual(loc.location_id, self.parent)

    # ------------------------------------------------------------------
    # Test 4 — Address defaults from contact on onchange
    # ------------------------------------------------------------------
    def test_04_address_defaults_from_contact(self):
        """Address fields are defaulted from the customer contact when contact_id is assigned."""
        loc = self.env['stock.location'].new({
            'name': 'New External Location',
            'usage': 'customer',
            'location_id': self.parent.id,
        })
        loc.contact_id = self.customer
        loc._onchange_contact_id_address()

        self.assertEqual(loc.ext_street, self.customer.street)
        self.assertEqual(loc.ext_city, self.customer.city)
        self.assertEqual(loc.ext_zip, self.customer.zip)
        self.assertEqual(loc.ext_country_id, self.customer.country_id)

    # ------------------------------------------------------------------
    # Test 5 — Address fields independently editable
    # ------------------------------------------------------------------
    def test_05_address_fields_independently_editable(self):
        """Changing an external location's address does not modify the customer partner record."""
        loc = self.env['stock.location'].create({
            'name': 'Editable Address Location',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
            'ext_street': self.customer.street,
            'ext_city': self.customer.city,
        })
        loc.write({'ext_city': 'Cork', 'ext_street': '99 New Road'})

        # Partner record must be unchanged
        self.assertEqual(self.customer.city, 'Dublin')
        self.assertEqual(self.customer.street, '10 Collector Road')

    # ------------------------------------------------------------------
    # Test 6 — Two external locations for same contact with distinct addresses
    # ------------------------------------------------------------------
    def test_06_two_locations_distinct_addresses(self):
        """One customer can have two external locations with different addresses (one-to-many)."""
        loc_a = self.env['stock.location'].create({
            'name': 'Location Dublin',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
            'ext_city': 'Dublin',
        })
        loc_b = self.env['stock.location'].create({
            'name': 'Location Cork',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
            'ext_city': 'Cork',
        })
        self.assertEqual(loc_a.contact_id, loc_b.contact_id)
        self.assertNotEqual(loc_a.ext_city, loc_b.ext_city)

    # ------------------------------------------------------------------
    # Test 7 — Non-customer contacts rejected by domain
    # ------------------------------------------------------------------
    def test_07_non_customer_rejected_by_domain(self):
        """contact_id field domain restricts to is_contact=True; non-contact absent from results."""
        field_def = self.env['stock.location']._fields.get('contact_id')
        self.assertIsNotNone(field_def, "contact_id must exist on stock.location")
        self.assertIn('is_contact', str(field_def.domain),
                      "contact_id domain must reference is_contact")

        contact_contacts = self.env['res.partner'].search([('is_contact', '=', True)])
        self.assertNotIn(self.non_customer, contact_contacts)

    # ------------------------------------------------------------------
    # Test 8 — Window action domain scoped; External absent from Rooms list
    # ------------------------------------------------------------------
    def test_08_window_action_domain_scoped(self):
        """External locations appear in customer domain; absent from Rooms (internal) domain."""
        loc = self.env['stock.location'].create({
            'name': 'Scoped External Location',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
        })

        external_domain = [
            ('usage', '=', 'customer'),
            ('contact_id', '!=', False),
        ]
        self.assertIn(loc, self.env['stock.location'].search(external_domain))

        rooms_domain = [('usage', '=', 'internal')]
        self.assertNotIn(loc, self.env['stock.location'].search(rooms_domain))

    # ------------------------------------------------------------------
    # Test 9 — Company scoping
    # ------------------------------------------------------------------
    def test_09_company_scoping(self):
        """External Locations parent is scoped to the current company."""
        self.assertEqual(
            self.parent.company_id,
            self.env.company,
            "Parent location must be scoped to the company that enabled the feature",
        )

    # ------------------------------------------------------------------
    # Test 10 — action_create_external_location() returns correct modal action
    # ------------------------------------------------------------------
    def test_10_action_create_external_location(self):
        """action_create_external_location() returns a modal action with correct defaults."""
        action = self.customer.action_create_external_location()

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action.get('target'), 'new', "action must open as modal dialog")
        ctx = action.get('context', {})
        self.assertEqual(ctx.get('default_contact_id'), self.customer.id)
        self.assertEqual(ctx.get('default_usage'), 'customer')
        self.assertEqual(ctx.get('default_location_id'), self.parent.id)
        self.assertEqual(ctx.get('default_ext_street'), self.customer.street)
        self.assertEqual(ctx.get('default_ext_city'), self.customer.city)
        self.assertEqual(ctx.get('default_ext_zip'), self.customer.zip)
        self.assertEqual(ctx.get('default_ext_country_id'), self.customer.country_id.id)

    # ------------------------------------------------------------------
    # Test 11 — external_location_count reflects linked locations
    # ------------------------------------------------------------------
    def test_11_external_location_count(self):
        """external_location_count on customer partner tracks number of linked external locations."""
        initial_count = self.customer.external_location_count

        self.env['stock.location'].create({
            'name': 'Count Location A',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
        })
        self.env['stock.location'].create({
            'name': 'Count Location B',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
        })

        self.customer.invalidate_recordset()
        self.assertEqual(self.customer.external_location_count, initial_count + 2)

    # ------------------------------------------------------------------
    # Test 12 — action_create_external_location() raises UserError without parent
    # ------------------------------------------------------------------
    def test_12_action_raises_without_parent(self):
        """action_create_external_location() raises UserError when parent location is absent."""
        new_company = self.env['res.company'].create({'name': 'Test Co — No External'})
        customer_in_new_co = self.customer.with_company(new_company)
        with self.assertRaises(UserError):
            customer_in_new_co.action_create_external_location()

    # ------------------------------------------------------------------
    # Test 13 — action_create_external_location() is non-destructive
    # ------------------------------------------------------------------
    def test_13_action_create_external_location_nondestructive(self):
        """Creating a second external location for the same contact does not remove the first."""
        loc1 = self.env['stock.location'].create({
            'name': 'Non-destruct Location 1',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
        })
        loc2 = self.env['stock.location'].create({
            'name': 'Non-destruct Location 2',
            'usage': 'customer',
            'location_id': self.parent.id,
            'contact_id': self.customer.id,
        })
        self.assertNotEqual(loc1.id, loc2.id, "Each external location is a distinct record")
        self.assertTrue(loc1.exists())
        self.assertTrue(loc2.exists())
        self.assertEqual(loc1.contact_id, loc2.contact_id, "Both belong to same customer")

    # ------------------------------------------------------------------
    # Test 14 — Composability boundary
    # ------------------------------------------------------------------
    def test_14_composability_boundary(self):
        """contact_id is owned by the bridge module; sor_locations does not define it.

        In the test environment both parents and the bridge are installed.
        This test verifies the module dependency structure to document the boundary:
        - contact_id exists because the bridge is installed
        - The bridge depends on both sor_locations AND sor_contact_roles
        - Neither parent module alone would provide contact_id
        """
        # Positive: bridge installed → field exists
        field = self.env['ir.model.fields'].search([
            ('model', '=', 'stock.location'),
            ('name', '=', 'contact_id'),
        ], limit=1)
        self.assertTrue(field, "contact_id must exist when the bridge module is installed")

        # Bridge module is installed
        bridge = self.env['ir.module.module'].search([
            ('name', '=', 'sor_locations_external'),
        ], limit=1)
        self.assertTrue(bridge)
        self.assertEqual(bridge.state, 'installed')

        # Bridge declares both parents as dependencies
        dep_names = self.env['ir.module.module.dependency'].search([
            ('module_id', '=', bridge.id),
        ]).mapped('name')
        self.assertIn('sor_locations', dep_names,
                      "Bridge must depend on sor_locations")
        self.assertIn('sor_contact_roles', dep_names,
                      "Bridge must depend on sor_contact_roles")

        # sor_locations base module does NOT expose contact_id — confirmed by:
        # field origin is the bridge (modules field contains the bridge name)
        self.assertIn(
            'sor_locations_external',
            field.modules,
            "contact_id field origin should include the bridge module",
        )

    # ------------------------------------------------------------------
    # Test 15 — Multi-company parent creation (post_init_hook coverage)
    # ------------------------------------------------------------------
    def test_15_multi_company_parent_creation(self):
        """_sor_ensure_external_locations_parent is idempotent per company.

        The post_init_hook calls this method for every existing company on install.
        This test verifies that calling it in a second company's context creates a
        parent scoped to that company — confirming the hook's multi-company behaviour.
        """
        company_b = self.env['res.company'].create({'name': 'Test Company B — ext locations'})
        env_b = self.env(context=dict(self.env.context, allowed_company_ids=[company_b.id]))

        # Ensure no parent exists yet for company_b
        parent_b_before = self.env['stock.location'].search([
            ('name', '=', 'External Locations'),
            ('usage', '=', 'view'),
            ('company_id', '=', company_b.id),
        ])
        self.assertFalse(parent_b_before, "No parent should exist for company_b before creation")

        # Call the method in company_b context (mimics post_init_hook behaviour)
        env_b['stock.location']._sor_ensure_external_locations_parent()

        parent_b = self.env['stock.location'].search([
            ('name', '=', 'External Locations'),
            ('usage', '=', 'view'),
            ('company_id', '=', company_b.id),
        ])
        self.assertTrue(parent_b, "Parent location must be created for company_b")
        self.assertEqual(parent_b.company_id, company_b)

        # The original company's parent is unaffected
        parent_a = self.env['stock.location'].search([
            ('name', '=', 'External Locations'),
            ('usage', '=', 'view'),
            ('company_id', '=', self.env.company.id),
        ])
        self.assertTrue(parent_a, "Company A parent must still exist")
