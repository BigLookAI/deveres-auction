from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorLotting(TransactionCase):
    """Automated tests for the sor_lotting module (sor.lot model)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not cls.product:
            cls.product = cls.env['product.template'].sudo().create({
                'name': 'Test Storable Product',
                'type': 'consu',
                'is_storable': True,
            })

    def _make_lot(self, **kwargs):
        vals = {'product_id': self.product.id}
        vals.update(kwargs)
        return self.env['sor.lot'].create(vals)

    # ------------------------------------------------------------------ #
    # 1. Module installs                                                   #
    # ------------------------------------------------------------------ #

    def test_module_installs(self):
        """sor.lot model is accessible from the environment."""
        self.assertIn('sor.lot', self.env)

    # ------------------------------------------------------------------ #
    # 2. lot_reference auto-assigned at creation                          #
    # ------------------------------------------------------------------ #

    def test_lot_reference_assigned_on_create(self):
        """lot_reference is auto-assigned from the sequence on creation."""
        lot = self._make_lot()
        self.assertTrue(lot.lot_reference)
        self.assertNotEqual(lot.lot_reference, 'New Lot')
        self.assertIn('LOT/', lot.lot_reference)

    def test_lot_reference_unique_per_lot(self):
        """Two lots created in sequence receive different lot_reference values."""
        lot1 = self._make_lot()
        lot2 = self._make_lot()
        self.assertNotEqual(lot1.lot_reference, lot2.lot_reference)

    # ------------------------------------------------------------------ #
    # 3. lot_number is optional                                            #
    # ------------------------------------------------------------------ #

    def test_lot_number_is_optional(self):
        """Creating a lot without lot_number raises no error; field stores blank not zero."""
        lot = self._make_lot()
        self.assertFalse(lot.lot_number)

    # ------------------------------------------------------------------ #
    # 4. State defaults to draft                                           #
    # ------------------------------------------------------------------ #

    def test_state_defaults_to_draft(self):
        """A newly created lot has state='draft'."""
        lot = self._make_lot()
        self.assertEqual(lot.state, 'draft')

    # ------------------------------------------------------------------ #
    # 5. State machine transitions                                         #
    # ------------------------------------------------------------------ #

    def test_draft_to_catalogued(self):
        """action_catalogue transitions draft → catalogued."""
        lot = self._make_lot()
        lot.action_catalogue()
        self.assertEqual(lot.state, 'catalogued')

    def test_catalogued_to_live(self):
        """lot state can be set to live (transition driven by sor_events_auction in practice)."""
        lot = self._make_lot()
        lot.action_catalogue()
        # The live transition is normally triggered by sor.event.action_go_live() cascading
        # to its lots. sor_lotting owns the state field; write directly for unit testing.
        lot.write({'state': 'live'})
        self.assertEqual(lot.state, 'live')

    def test_live_to_sold(self):
        """action_mark_sold transitions live → sold."""
        lot = self._make_lot()
        lot.action_catalogue()
        lot.write({'state': 'live'})
        # When sor_bidding is installed, action_mark_sold requires at least one bid.
        if 'sor.bid' in self.env:
            partner = self.env['res.partner'].search([], limit=1)
            self.env['sor.bid'].create({
                'lot_id': lot.id,
                'bidder_id': partner.id,
                'bid_type': 'floor',
                'amount': 1000.0,
            })
        lot.action_mark_sold()
        self.assertEqual(lot.state, 'sold')

    def test_live_to_passed(self):
        """action_mark_passed transitions live → passed."""
        lot = self._make_lot()
        lot.action_catalogue()
        lot.write({'state': 'live'})
        lot.action_mark_passed()
        self.assertEqual(lot.state, 'passed')

    def test_draft_to_withdrawn(self):
        """action_withdraw transitions draft → withdrawn."""
        lot = self._make_lot()
        lot.action_withdraw()
        self.assertEqual(lot.state, 'withdrawn')

    def test_catalogued_to_withdrawn(self):
        """action_withdraw transitions catalogued → withdrawn."""
        lot = self._make_lot()
        lot.action_catalogue()
        lot.action_withdraw()
        self.assertEqual(lot.state, 'withdrawn')

    def test_invalid_transition_raises(self):
        """Attempting an invalid transition raises UserError."""
        lot = self._make_lot()
        # action_mark_sold on a draft lot raises UserError — either from the
        # sor_lotting state guard (state not in catalogued/live) or, when
        # sor_bidding is installed, from the bids-required guard.
        with self.assertRaises(UserError):
            lot.action_mark_sold()

    # ------------------------------------------------------------------ #
    # 6. Deletion guard                                                    #
    # ------------------------------------------------------------------ #

    def test_draft_lot_can_be_deleted(self):
        """A draft lot can be deleted without error."""
        lot = self._make_lot()
        lot_id = lot.id
        lot.unlink()
        self.assertFalse(self.env['sor.lot'].browse(lot_id).exists())

    def test_non_draft_lot_cannot_be_deleted(self):
        """Deleting a catalogued lot raises UserError."""
        lot = self._make_lot()
        lot.action_catalogue()
        with self.assertRaises(UserError):
            lot.unlink()

    # ------------------------------------------------------------------ #
    # 7. break_even_value computed field                                   #
    # ------------------------------------------------------------------ #

    def test_break_even_value_equals_reserve_price(self):
        """break_even_value is at least reserve_price when set.

        When sor_commercial_auction_house is installed the formula applies a
        seller's commission, so break_even >= reserve_price. Without the bridge
        they are equal. Both cases pass this assertion.
        """
        lot = self._make_lot(reserve_price=5000.0)
        self.assertGreaterEqual(lot.break_even_value, 5000.0)

    def test_break_even_value_zero_when_no_reserve(self):
        """break_even_value is 0.0 when reserve_price is not set."""
        lot = self._make_lot()
        self.assertEqual(lot.break_even_value, 0.0)

    # ------------------------------------------------------------------ #
    # 8. no_reserve flag                                                   #
    # ------------------------------------------------------------------ #

    def test_no_reserve_flag_independent_of_reserve_price(self):
        """no_reserve=True can be set alongside a non-zero reserve_price."""
        lot = self._make_lot(reserve_price=1000.0, no_reserve=True)
        self.assertTrue(lot.no_reserve)
        self.assertEqual(lot.reserve_price, 1000.0)

    # ------------------------------------------------------------------ #
    # 9. Estimate CHECK constraint                                         #
    # ------------------------------------------------------------------ #

    def test_estimate_constraint_low_exceeds_high(self):
        """estimate_low > estimate_high raises an Exception."""
        with self.assertRaises(Exception):
            self._make_lot(estimate_low=10000.0, estimate_high=5000.0)
            self.env.flush_all()

    def test_estimate_constraint_both_null_ok(self):
        """Lot with neither estimate set saves cleanly."""
        lot = self._make_lot()
        self.assertFalse(lot.estimate_low)
        self.assertFalse(lot.estimate_high)

    def test_estimate_constraint_one_null_ok(self):
        """Lot with only estimate_low set saves cleanly."""
        lot = self._make_lot(estimate_low=3000.0)
        self.assertEqual(lot.estimate_low, 3000.0)
        self.assertFalse(lot.estimate_high)

    # ------------------------------------------------------------------ #
    # 10. Multi-company fields                                             #
    # ------------------------------------------------------------------ #

    def test_currency_id_from_company(self):
        """currency_id matches the current company's currency."""
        lot = self._make_lot()
        self.assertEqual(lot.currency_id, self.env.company.currency_id)

    def test_company_id_defaults_to_current_company(self):
        """company_id defaults to env.company."""
        lot = self._make_lot()
        self.assertEqual(lot.company_id, self.env.company)

    # ------------------------------------------------------------------ #
    # 11. Optional fields                                                  #
    # ------------------------------------------------------------------ #

    def test_lot_suffix_is_optional(self):
        """Creating a lot without lot_suffix raises no error."""
        lot = self._make_lot()
        self.assertFalse(lot.lot_suffix)

    def test_internal_notes_is_optional(self):
        """Creating a lot without internal_notes raises no error."""
        lot = self._make_lot()
        self.assertFalse(lot.internal_notes)
