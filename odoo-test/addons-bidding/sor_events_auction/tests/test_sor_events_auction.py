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

    def test_12_action_go_live_raises_when_draft_lots_present(self):
        """action_go_live raises UserError when Draft lots remain — all lots must be catalogued.

        Story 03 (Catalogue All Lots + Go Live Guard) changed the behaviour: draft lots
        are no longer silently skipped; instead the guard blocks Go Live entirely.
        Explicit lot_numbers avoid the sor_lot_auction_lot_number_unique constraint
        collision that arises when two NULL lot_numbers share the same auction.
        """
        event = self.env['sor.event'].create({
            'name': 'Draft Guard Test Auction',
            'event_type': 'auction',
            'status': 'published',
            'date_start': '2026-05-25 10:00:00',
            'company_id': self.env.company.id,
        })
        draft_lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event.id,
            'lot_number': 'D01',
            'state': 'draft',
        })
        catalogued_lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': event.id,
            'lot_number': 'C01',
            'state': 'catalogued',
        })
        with self.assertRaises(UserError,
                               msg="action_go_live must raise UserError when Draft lots remain"):
            event.action_go_live()
        self.assertEqual(event.status, 'published',
                         "Event must remain Published after go_live guard fires.")
        self.assertEqual(draft_lot.state, 'draft',
                         "Draft lot must remain in Draft after go_live guard fires.")
        self.assertEqual(catalogued_lot.state, 'catalogued',
                         "Catalogued lot must remain Catalogued when guard blocks go_live.")

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
    # 7. Chatter — action_go_live posts a message (Sprint 19)
    # ------------------------------------------------------------------

    def test_17_action_go_live_posts_chatter_message(self):
        """action_go_live posts a message to the auction event chatter."""
        event = self.env['sor.event'].create({
            'name': 'Chatter Go Live Test',
            'event_type': 'auction',
            'status': 'published',
            'date_start': '2026-07-01 10:00:00',
            'company_id': self.env.company.id,
        })
        before_count = len(event.message_ids)
        event.action_go_live()
        self.assertGreater(
            len(event.message_ids), before_count,
            'action_go_live must post a chatter message',
        )

    # ------------------------------------------------------------------
    # 8. action_catalogue guard — late cataloguing blocked when auction is Live
    # ------------------------------------------------------------------

    def test_18_action_catalogue_blocked_when_auction_is_live(self):
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

    # ------------------------------------------------------------------
    # 9. Story 04 — Auction Lot Dedicated View
    # ------------------------------------------------------------------

    def test_19_action_catalogue_selected_lots_catalogues_draft_lots(self):
        """action_catalogue_selected_lots catalogues every Draft lot in the recordset."""
        lots = self.env['sor.lot'].create([
            {
                'product_id': self.product.id,
                'company_id': self.env.company.id,
                'auction_id': self.auction.id,
                'lot_number': 'S4-01',
            },
            {
                'product_id': self.product.id,
                'company_id': self.env.company.id,
                'auction_id': self.auction.id,
                'lot_number': 'S4-02',
            },
        ])
        lots.action_catalogue_selected_lots()
        self.assertTrue(all(lot.state == 'catalogued' for lot in lots))

    def test_20_action_catalogue_selected_lots_silently_skips_non_draft(self):
        """action_catalogue_selected_lots is a safe no-op on already-Catalogued/Sold lots (Finding #1).

        Confirmed non-blocking at Show & Tell: the header button itself cannot be gated on
        selected-row state (see odoo_conventions/view_patterns.md), so the Python method must
        be defensive. This test locks in that the defensiveness itself is correct: mixing
        already-catalogued lots into the selection does not raise and does not change their state.
        """
        draft_lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': self.auction.id,
            'lot_number': 'S4-03',
        })
        catalogued_lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': self.auction.id,
            'lot_number': 'S4-04',
        })
        catalogued_lot.action_catalogue()
        mixed_selection = draft_lot | catalogued_lot
        mixed_selection.action_catalogue_selected_lots()
        self.assertEqual(draft_lot.state, 'catalogued')
        self.assertEqual(catalogued_lot.state, 'catalogued')

    def test_21_action_catalogue_selected_lots_still_guards_missing_lot_number(self):
        """The existing 'no lot_number' guard in action_catalogue is unchanged by this story."""
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'auction_id': self.auction.id,
        })
        with self.assertRaises(UserError):
            lot.action_catalogue_selected_lots()

    def test_22_server_action_catalogue_all_lots_removed(self):
        """The old global server action action_catalogue_all_lots no longer exists."""
        action = self.env['ir.actions.server'].search([
            ('name', '=', 'Catalogue Selected Lots'),
            ('model_id.model', '=', 'sor.lot'),
        ])
        self.assertFalse(
            action, 'The global server action must be removed — replaced by a header button',
        )

    def test_23_dedicated_view_contains_auction_context_columns_and_header_button(self):
        """The dedicated Auction Lot list view combined arch has auction_id, hammer_price, and the header button."""
        arch = self.env.ref(
            'sor_events_auction.sor_lot_view_list_auction_dedicated',
        ).get_combined_arch()
        self.assertIn('auction_id', arch)
        self.assertIn('hammer_price', arch)
        self.assertIn('action_catalogue_selected_lots', arch)
        # auction_id must appear exactly once (see Developer Notes — mode="primary" combined
        # arch already inherits sor_lot_view_list_auction_id's contribution automatically)
        self.assertEqual(arch.count('name="auction_id"'), 1)

    def test_24_lots_stat_button_bound_to_dedicated_view(self):
        """The event's 'Lots' stat button action is bound to the dedicated view for list mode."""
        action = self.env.ref('sor_events_auction.sor_lot_action_from_event')
        binding = self.env['ir.actions.act_window.view'].search([
            ('act_window_id', '=', action.id),
            ('view_mode', '=', 'list'),
        ])
        self.assertTrue(binding, 'A list-mode view binding must exist for sor_lot_action_from_event')
        self.assertEqual(
            binding.view_id,
            self.env.ref('sor_events_auction.sor_lot_view_list_auction_dedicated'),
        )
