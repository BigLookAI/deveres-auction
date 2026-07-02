# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorLocations(TransactionCase):
    """Tests for sor_locations: Viewing Locations and Rooms."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Warehouse = cls.env['stock.warehouse']
        cls.Location = cls.env['stock.location']

    def test_create_viewing_location_with_rooms(self):
        """Create 1 Viewing Location with 2 Rooms; assert Rooms are internal
        and warehouse_id points to the Viewing Location."""
        wh = self.Warehouse.create({
            'name': 'Test Gallery — sor_locations suite',
            'code': 'TSLG',
        })
        room1 = self.Location.create({
            'name': 'Gallery Floor',
            'usage': 'internal',
            'location_id': wh.view_location_id.id,
        })
        room2 = self.Location.create({
            'name': 'Storage',
            'usage': 'internal',
            'location_id': wh.view_location_id.id,
        })
        self.assertEqual(room1.usage, 'internal')
        self.assertEqual(room2.usage, 'internal')
        self.assertEqual(room1.warehouse_id, wh)
        self.assertEqual(room2.warehouse_id, wh)

    def test_create_multiple_viewing_locations(self):
        """Create 2 Viewing Locations each with 2 Rooms; assert independent
        hierarchy (SETU pilot case: multiple buildings)."""
        wh1 = self.Warehouse.create({
            'name': 'Test Building A — sor_locations suite',
            'code': 'TSBA',
        })
        wh2 = self.Warehouse.create({
            'name': 'Test Building B — sor_locations suite',
            'code': 'TSBB',
        })
        room_a1 = self.Location.create({
            'name': 'Room A1',
            'usage': 'internal',
            'location_id': wh1.view_location_id.id,
        })
        room_a2 = self.Location.create({
            'name': 'Room A2',
            'usage': 'internal',
            'location_id': wh1.view_location_id.id,
        })
        room_b1 = self.Location.create({
            'name': 'Room B1',
            'usage': 'internal',
            'location_id': wh2.view_location_id.id,
        })
        room_b2 = self.Location.create({
            'name': 'Room B2',
            'usage': 'internal',
            'location_id': wh2.view_location_id.id,
        })
        self.assertEqual(room_a1.warehouse_id, wh1)
        self.assertEqual(room_a2.warehouse_id, wh1)
        self.assertEqual(room_b1.warehouse_id, wh2)
        self.assertEqual(room_b2.warehouse_id, wh2)
        self.assertNotEqual(room_a1.warehouse_id, room_b1.warehouse_id)

    def test_default_address_from_company(self):
        """Create a Viewing Location without specifying partner_id; assert it
        defaults to the company's partner address."""
        wh = self.Warehouse.create({
            'name': 'Gallery Default Address',
            'code': 'GDA1',
        })
        self.assertEqual(wh.partner_id, self.env.company.partner_id)

    def test_partner_required_constraint(self):
        """Attempt to create a Viewing Location with no partner_id; assert
        ValidationError is raised."""
        with self.assertRaises(ValidationError):
            self.Warehouse.create({
                'name': 'No Address Gallery',
                'code': 'NAGX',
                'partner_id': False,
            })

    def test_storage_locations_enabled_after_install(self):
        """Assert that the Storage Locations group is active after module
        installation (i.e. post_init_hook ran successfully)."""
        self.assertTrue(
            self.env.user.has_group('stock.group_stock_multi_locations'),
            "Storage Locations group should be enabled by post_init_hook",
        )

    def test_company_scoping(self):
        """Create a Viewing Location in Company A; assert it is not visible
        to a user whose access is restricted to a different company.

        Uses a restricted user (not admin) because ORM record rules filter by
        user.company_ids, not by allowed_company_ids context. Admin has access
        to all companies by default, so context alone does not restrict search.
        """
        company_a = self.env['res.company'].create({'name': 'SOR Test Company A Scoping'})
        wh = self.env['stock.warehouse'].sudo().with_company(company_a).create({
            'name': 'SOR Scoping Test Gallery',
            'code': 'SSTG',
            'partner_id': company_a.partner_id.id,
        })
        self.assertEqual(wh.company_id, company_a)

        # Create a user restricted to the current company only (no access to company_a)
        user_b = self.env['res.users'].create({
            'name': 'Company B Restricted User',
            'login': 'user_b_scoping@sortest.example',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, [self.env.company.id])],
        })
        results = self.env['stock.warehouse'].with_user(user_b).search([
            ('name', '=', 'SOR Scoping Test Gallery'),
        ])
        self.assertFalse(
            results,
            "Viewing Location from Company A should not appear to a user restricted to Company B",
        )

    def test_stock_menus_suppressed(self):
        """Standard Warehouses and Locations menus must be inactive while
        sor_locations is installed (menu_overrides.xml + uninstall_hook)."""
        warehouse_menu = self.env.ref(
            'stock.menu_action_warehouse_form', raise_if_not_found=False,
        )
        location_menu = self.env.ref(
            'stock.menu_action_location_form', raise_if_not_found=False,
        )
        if warehouse_menu:
            self.assertFalse(
                warehouse_menu.active,
                "Standard Warehouses menu should be suppressed by sor_locations",
            )
        if location_menu:
            self.assertFalse(
                location_menu.active,
                "Standard Locations menu should be suppressed by sor_locations",
            )

    def test_room_parent_must_be_viewing_location(self):
        """A Room cannot have another Room as its parent; only a Viewing
        Location's top-level location is a valid parent."""
        wh = self.Warehouse.create({
            'name': 'Parent Constraint Gallery',
            'code': 'PCGV',
        })
        room1 = self.Location.create({
            'name': 'Room A',
            'usage': 'internal',
            'location_id': wh.view_location_id.id,
        })
        with self.assertRaises(ValidationError):
            self.Location.create({
                'name': 'Nested Room',
                'usage': 'internal',
                'location_id': room1.id,  # parent is a Room, not a VL
            })

    def test_viewing_location_id_alias_on_room(self):
        """Assert that viewing_location_id on stock.location is a readable alias
        for warehouse_id pointing to the parent Viewing Location."""
        wh = self.Warehouse.create({
            'name': 'Alias Test Gallery',
            'code': 'ATGV',
        })
        room = self.Location.create({
            'name': 'Main Hall',
            'usage': 'internal',
            'location_id': wh.view_location_id.id,
        })
        self.assertEqual(room.viewing_location_id, wh)
        self.assertEqual(room.viewing_location_id, room.warehouse_id)
