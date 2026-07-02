from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorEventsAuction(TransactionCase):
    """Automated tests for the sor_events_auction bridge module.

    Covers: module installs, lot assignment, duplicate lot number constraint,
    lot_count computed field, action_go_live cascade behaviour, draft lot
    exclusion, live state composability (absent from sor_lotting alone), and
    action_catalogue guard that blocks late cataloguing when auction is Active.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Shared product required for lot creation — search first so sor_artwork's
        # creator_required constraint is not triggered by test data creation.
        cls.product = cls.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not cls.product:
            msg = "No storable product found in database — cannot run sor_events_auction tests"
            raise RuntimeError(msg)

        # A published auction event — the valid pre-condition for action_go_live
        cls.auction = cls.env['sor.event'].create({
            'name': 'Spring Sale 2026',
            'event_type': 'auction',
            'status': 'published',
            'date_start': '2026-05-01 10:00:00',
            'company_id': cls.env.company.id,
        })

    # ------------------------------------------------------------------
    # 1. Module installs — key models and fields are accessible
    # ------------------------------------------------------------------

    def test_01_module_installs_sor_event_fields(self):
        """Bridge adds expected fields to sor.event."""
        event = self.env['sor.event'].create({
            'name': 'Module Install Check',
            'event_type': 'auction',
            'status': 'draft',
            'date_start': '2026-06-01 10:00:00',
            'company_id': self.env.company.id,
        })
        self.assertIn('auction_subtype', event._fields)
        self.assertIn('sale_number', event._fields)
        self.assertIn('preview_start', event._fields)
        self.assertIn('preview_end', event._fields)
        self.assertIn('lot_ids', event._fields)
        self.assertIn('lot_count', event._fields)

    def test_02_module_installs_sor_lot_fields(self):
        """Bridge adds auction_id field to sor.lot."""
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
        })
        self.assertIn('auction_id', lot._fields)

    # ------------------------------------------------------------------
    # 2. Lot assignment — a lot can be assigned to one auction
    # ------------------------------------------------------------------

    def test_03_lot_can_be_assigned_to_auction(self):
        """A lot can be assigned to an auction via auction_id."""
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': self.auction.id,
        })
        self.assertEqual(lot.auction_id, self.auction)

    def test_04_lot_auction_id_optional(self):
        """auction_id is optional — a lot with no auction assignment is valid."""
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
        })
        self.assertFalse(lot.auction_id)

    # ------------------------------------------------------------------
    # 3. Duplicate lot number constraint
    # ------------------------------------------------------------------

    def test_05_duplicate_lot_number_within_auction_raises(self):
        """Two lots with the same lot_number in the same auction raise a constraint error."""
        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': self.auction.id,
            'lot_number': '001',
        })
        with self.assertRaises(Exception):
            self.env['sor.lot'].create({
                'product_id': self.product.id,
                'company_id': self.env.company.id,
                'auction_id': self.auction.id,
                'lot_number': '001',
            })

    def test_06_same_lot_number_in_different_auctions_is_valid(self):
        """The same lot_number may appear in different auctions without constraint violation."""
        second_auction = self.env['sor.event'].create({
            'name': 'Autumn Sale 2026',
            'event_type': 'auction',
            'status': 'draft',
            'date_start': '2026-10-01 10:00:00',
            'company_id': self.env.company.id,
        })
        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': self.auction.id,
            'lot_number': '001',
        })
        # Should not raise — same number in a different auction is allowed.
        lot_b = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': second_auction.id,
            'lot_number': '001',
        })
        self.assertEqual(lot_b.lot_number, '001')

    def test_07_same_lot_number_no_auction_is_valid(self):
        """Two lots with the same lot_number but no auction are not in conflict."""
        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'lot_number': 'A1',
        })
        lot_b = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'lot_number': 'A1',
        })
        self.assertEqual(lot_b.lot_number, 'A1')

    # ------------------------------------------------------------------
    # 4. lot_count computed field
    # ------------------------------------------------------------------

    def test_08_lot_count_reflects_assigned_lots(self):
        """lot_count on sor.event equals the number of lots assigned via auction_id."""
        # Isolate this test with a fresh event.
        event = self.env['sor.event'].create({
            'name': 'lot_count Test Auction',
            'event_type': 'auction',
            'status': 'draft',
            'date_start': '2026-07-01 10:00:00',
            'company_id': self.env.company.id,
        })
        self.assertEqual(event.lot_count, 0)

        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event.id,
        })
        self.assertEqual(event.lot_count, 1)

        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event.id,
        })
        self.assertEqual(event.lot_count, 2)

    def test_09_lot_count_excludes_unassigned_lots(self):
        """lot_count does not count lots assigned to other events or unassigned lots."""
        event_a = self.env['sor.event'].create({
            'name': 'Isolation Test Auction A',
            'event_type': 'auction',
            'status': 'draft',
            'date_start': '2026-08-01 10:00:00',
            'company_id': self.env.company.id,
        })
        event_b = self.env['sor.event'].create({
            'name': 'Isolation Test Auction B',
            'event_type': 'auction',
            'status': 'draft',
            'date_start': '2026-09-01 10:00:00',
            'company_id': self.env.company.id,
        })
        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event_b.id,
        })
        # event_a has no lots — count must remain 0.
        self.assertEqual(event_a.lot_count, 0)

    # ------------------------------------------------------------------
    # 5. action_go_live — state transitions
    # ------------------------------------------------------------------

    def test_10_action_go_live_transitions_event_to_active(self):
        """action_go_live sets the auction event status to 'active'."""
        event = self.env['sor.event'].create({
            'name': 'Go Live Test Auction',
            'event_type': 'auction',
            'status': 'published',
            'date_start': '2026-05-15 10:00:00',
            'company_id': self.env.company.id,
        })
        event.action_go_live()
        self.assertEqual(event.status, 'active')

    def test_11_action_go_live_cascades_catalogued_lots(self):
        """action_go_live transitions all Catalogued lots on the event to Live."""
        event = self.env['sor.event'].create({
            'name': 'Cascade Test Auction',
            'event_type': 'auction',
            'status': 'published',
            'date_start': '2026-05-20 10:00:00',
            'company_id': self.env.company.id,
        })
        lot_a = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event.id,
            'state': 'catalogued',
        })
        lot_b = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event.id,
            'state': 'catalogued',
        })
        event.action_go_live()
        self.assertEqual(lot_a.state, 'live')
        self.assertEqual(lot_b.state, 'live')

    def test_12_action_go_live_excludes_draft_lots(self):
        """action_go_live does not transition Draft lots — only Catalogued lots are affected."""
        event = self.env['sor.event'].create({
            'name': 'Draft Exclusion Test Auction',
            'event_type': 'auction',
            'status': 'published',
            'date_start': '2026-05-25 10:00:00',
            'company_id': self.env.company.id,
        })
        draft_lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event.id,
            'state': 'draft',
        })
        catalogued_lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event.id,
            'state': 'catalogued',
        })
        event.action_go_live()
        self.assertEqual(draft_lot.state, 'draft',
                         "Draft lots must remain in Draft after Go Live.")
        self.assertEqual(catalogued_lot.state, 'live',
                         "Catalogued lots must move to Live after Go Live.")

    def test_13_action_go_live_raises_if_not_published(self):
        """action_go_live raises UserError if the event is not in Published state."""
        draft_event = self.env['sor.event'].create({
            'name': 'Draft Guard Test Auction',
            'event_type': 'auction',
            'status': 'draft',
            'date_start': '2026-06-01 10:00:00',
            'company_id': self.env.company.id,
        })
        with self.assertRaises(UserError):
            draft_event.action_go_live()

    def test_14_action_go_live_ignores_lots_from_other_auctions(self):
        """action_go_live only cascades lots assigned to the triggering auction."""
        event_a = self.env['sor.event'].create({
            'name': 'Scope Test Auction A',
            'event_type': 'auction',
            'status': 'published',
            'date_start': '2026-06-10 10:00:00',
            'company_id': self.env.company.id,
        })
        event_b = self.env['sor.event'].create({
            'name': 'Scope Test Auction B',
            'event_type': 'auction',
            'status': 'published',
            'date_start': '2026-06-20 10:00:00',
            'company_id': self.env.company.id,
        })
        lot_b = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event_b.id,
            'state': 'catalogued',
        })
        # Go Live on event_a must not touch event_b's lots.
        event_a.action_go_live()
        lot_b.invalidate_recordset(['state'])
        self.assertEqual(lot_b.state, 'catalogued',
                         "Lots on a different auction must not be affected by Go Live.")

    # ------------------------------------------------------------------
    # 6. live state composability — absent from sor_lotting standalone
    # ------------------------------------------------------------------

    def test_15_live_state_exists_on_sor_lot(self):
        """The 'live' state value is present in sor.lot.state when the bridge is installed."""
        state_values = [v for v, _ in self.env['sor.lot']._fields['state'].selection]
        self.assertIn('live', state_values,
                      "The 'live' state must be present when sor_events_auction is installed.")

    def test_16_live_state_defined_by_selection_add(self):
        """The 'live' state is contributed by the bridge, not the base sor_lotting module.

        Verified indirectly: the base sor.lot model does not include 'live' in its
        own selection list — only after sor_events_auction installs via selection_add
        does it appear. When the bridge is installed this test confirms its presence;
        the absence test is by definition only verifiable in a sor_lotting-only install.
        """
        state_values = [v for v, _ in self.env['sor.lot']._fields['state'].selection]
        # Base states from sor_lotting
        base_states = ['draft', 'catalogued', 'sold', 'passed', 'withdrawn']
        for base_state in base_states:
            self.assertIn(base_state, state_values,
                          f"Base state '{base_state}' must remain after bridge install.")
        # Bridge-contributed state
        self.assertIn('live', state_values,
                      "Bridge must add 'live' state via selection_add.")

    # ------------------------------------------------------------------
    # 7. action_catalogue guard — late cataloguing blocked when auction is Live
    # ------------------------------------------------------------------

    def test_17_action_catalogue_blocked_when_auction_is_live(self):
        """action_catalogue raises UserError when the lot's auction is already Active."""
        active_auction = self.env['sor.event'].create({
            'name': 'Active Auction for Catalogue Guard Test',
            'event_type': 'auction',
            'status': 'active',
            'date_start': '2026-05-01 10:00:00',
            'company_id': self.env.company.id,
        })
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': active_auction.id,
        })
        with self.assertRaises(UserError,
                               msg="action_catalogue must raise UserError when auction is Active"):
            lot.action_catalogue()
        self.assertEqual(lot.state, 'draft',
                         "Lot must remain in Draft when catalogue guard raises")
