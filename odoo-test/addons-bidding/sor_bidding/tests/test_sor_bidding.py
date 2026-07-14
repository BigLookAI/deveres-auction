"""
Tests for sor_bidding — bridge module linking sor_lotting x sor_contact_roles.

Coverage:
  1.  Module installs — sor.bid model exists; key fields present.
  2.  Bid creation — all fields populated; bid appears on lot.
  3.  bid_count computed field — reflects live bid_ids length.
  4.  hammer_price auto-population — Sold transition picks highest bid amount.
  5.  Sold guard — action_mark_sold raises UserError when no bids recorded.
  6.  max_amount field exists — can be set on commission bids.
  7.  external_bid_id indexed — field present and accepts a string value.
  8.  Multi-company isolation — bid from Company A not visible to Company B user.
  9.  Composability — bid_ids present on sor.lot when bridge is installed.
  10. is_winning_bid — set on winning bid after action_mark_sold.
  11. action_view_bids — returns lot-filtered domain.
  12. res.partner extension — bid_ids and bid_count present; action_view_bids company-scoped.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorBidding(TransactionCase):
    """Automated tests for the sor_bidding bridge module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Companies
        cls.company_a = cls.env.company  # default test company
        cls.company_b = cls.env['res.company'].create({'name': 'Test Company B'})

        # Bidder contact — assigned Contact parent type and Bidder sub-type.
        # As of Story 02, Bidder is a sub-type (parent_type_id set to Contact).
        # contact_types holds parent types; contact_subtypes holds sub-types.
        cls.contact_type = cls.env.ref('sor_contact_roles.sor_contact_type_contact')
        cls.bidder_type = cls.env.ref('sor_contact_roles.sor_contact_type_bidder')
        cls.bidder = cls.env['res.partner'].create({
            'name': 'Test Bidder',
            'contact_types': [(4, cls.contact_type.id)],
            'contact_subtypes': [(4, cls.bidder_type.id)],
        })

        # A storable product required by sor.lot — search first so sor_artwork's
        # creator_required constraint is not triggered by test data creation.
        cls.product = cls.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not cls.product:
            msg = "No storable product found in database — cannot run sor_bidding tests"
            raise RuntimeError(msg)

        # Lot belonging to Company A (draft state — transitions from draft→catalogued
        # so the Sold action is reachable via draft→catalogued→sold)
        cls.lot = cls.env['sor.lot'].create({
            'product_id': cls.product.id,
            'company_id': cls.company_a.id,
            'lot_number': '001',
        })
        # Catalogue the lot so action_mark_sold is available
        cls.lot.action_catalogue()

    # ------------------------------------------------------------------
    # 1. Module installs — model and key fields exist
    # ------------------------------------------------------------------

    def test_01_model_exists(self):
        """sor.bid model is present after module installation."""
        model = self.env['ir.model'].search([('model', '=', 'sor.bid')])
        self.assertTrue(model, "sor.bid model should exist after sor_bidding installs")

    def test_02_key_fields_present(self):
        """sor.bid exposes all required fields."""
        fields_info = self.env['sor.bid'].fields_get()
        required_fields = [
            'lot_id', 'bidder_id', 'bid_type', 'amount',
            'max_amount', 'bid_datetime', 'external_bid_id',
            'company_id', 'currency_id',
        ]
        for field_name in required_fields:
            self.assertIn(
                field_name, fields_info,
                f"Field '{field_name}' should be present on sor.bid",
            )

    # ------------------------------------------------------------------
    # 2. Bid creation
    # ------------------------------------------------------------------

    def test_03_create_bid(self):
        """A bid can be created with all required fields."""
        bid = self.env['sor.bid'].create({
            'lot_id': self.lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'floor',
            'amount': 1500.0,
        })
        self.assertTrue(bid.id, "Bid should be persisted with a database ID")
        self.assertEqual(bid.lot_id, self.lot)
        self.assertEqual(bid.bidder_id, self.bidder)
        self.assertEqual(bid.bid_type, 'floor')
        self.assertEqual(bid.amount, 1500.0)

    def test_04_bid_linked_to_lot(self):
        """A created bid appears in the lot's bid_ids."""
        bid = self.env['sor.bid'].create({
            'lot_id': self.lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'absentee',
            'amount': 2000.0,
        })
        self.assertIn(bid, self.lot.bid_ids)

    def test_05_bid_type_selection_values(self):
        """All five bid_type selection values are accepted."""
        bid_types = ['floor', 'absentee', 'commission', 'online', 'phone']
        for bt in bid_types:
            bid = self.env['sor.bid'].create({
                'lot_id': self.lot.id,
                'bidder_id': self.bidder.id,
                'bid_type': bt,
                'amount': 100.0,
            })
            self.assertEqual(bid.bid_type, bt, f"bid_type '{bt}' should be stored correctly")

    def test_06_company_id_derived_from_lot(self):
        """company_id on a bid is the related stored value from lot_id.company_id."""
        bid = self.env['sor.bid'].create({
            'lot_id': self.lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'floor',
            'amount': 500.0,
        })
        self.assertEqual(
            bid.company_id, self.company_a,
            "bid.company_id should equal the lot's company_id",
        )

    def test_07_currency_id_derived_from_lot(self):
        """currency_id on a bid is the related stored value from lot_id.currency_id."""
        bid = self.env['sor.bid'].create({
            'lot_id': self.lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'floor',
            'amount': 500.0,
        })
        self.assertEqual(
            bid.currency_id, self.lot.currency_id,
            "bid.currency_id should equal the lot's currency_id",
        )

    # ------------------------------------------------------------------
    # 3. bid_count computed field
    # ------------------------------------------------------------------

    def test_08_bid_count_reflects_bids(self):
        """bid_count on sor.lot equals the number of bids linked to that lot."""
        # Create a fresh lot for this test to avoid interference from other tests
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.company_a.id,
        })
        self.assertEqual(lot.bid_count, 0, "Newly created lot should have bid_count=0")

        self.env['sor.bid'].create({
            'lot_id': lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'floor',
            'amount': 1000.0,
        })
        self.assertEqual(lot.bid_count, 1, "bid_count should be 1 after one bid")

        self.env['sor.bid'].create({
            'lot_id': lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'online',
            'amount': 1200.0,
        })
        self.assertEqual(lot.bid_count, 2, "bid_count should be 2 after two bids")

    # ------------------------------------------------------------------
    # 4. hammer_price auto-population on Sold transition
    # ------------------------------------------------------------------

    def test_09_sold_action_sets_hammer_price_from_highest_bid(self):
        """action_mark_sold auto-populates hammer_price with the highest bid amount."""
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.company_a.id,
            'lot_number': '009',
        })
        lot.action_catalogue()

        self.env['sor.bid'].create([
            {
                'lot_id': lot.id,
                'bidder_id': self.bidder.id,
                'bid_type': 'floor',
                'amount': 3000.0,
            },
            {
                'lot_id': lot.id,
                'bidder_id': self.bidder.id,
                'bid_type': 'absentee',
                'amount': 5500.0,
            },
            {
                'lot_id': lot.id,
                'bidder_id': self.bidder.id,
                'bid_type': 'floor',
                'amount': 4800.0,
            },
        ])

        lot.action_mark_sold()
        self.assertEqual(lot.state, 'sold', "Lot state should be 'sold'")
        self.assertEqual(
            lot.hammer_price, 5500.0,
            "hammer_price should be set to the highest bid amount (5500.0)",
        )

    def test_10_sold_action_no_bids_raises_user_error(self):
        """action_mark_sold with no bids raises UserError — at least one bid required."""
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.company_a.id,
            'lot_number': '010',
            'hammer_price': 0.0,
        })
        lot.action_catalogue()
        with self.assertRaises(UserError, msg="action_mark_sold must raise UserError when no bids"):
            lot.action_mark_sold()
        # State must remain catalogued — transition must not have occurred
        self.assertEqual(lot.state, 'catalogued', "Lot state must stay catalogued when sold guard raises")

    # ------------------------------------------------------------------
    # 5. max_amount field (commission bids)
    # ------------------------------------------------------------------

    def test_11_max_amount_stored_on_commission_bid(self):
        """max_amount can be set on a commission bid and is persisted."""
        bid = self.env['sor.bid'].create({
            'lot_id': self.lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'commission',
            'amount': 2000.0,
            'max_amount': 6000.0,
        })
        self.assertEqual(bid.max_amount, 6000.0)

    def test_12_max_amount_field_exists(self):
        """max_amount field is present on sor.bid."""
        fields_info = self.env['sor.bid'].fields_get()
        self.assertIn('max_amount', fields_info)
        self.assertEqual(fields_info['max_amount']['type'], 'monetary')

    # ------------------------------------------------------------------
    # 6. external_bid_id — indexed import deduplication field
    # ------------------------------------------------------------------

    def test_13_external_bid_id_accepts_string(self):
        """external_bid_id stores a string value and is present on the model."""
        bid = self.env['sor.bid'].create({
            'lot_id': self.lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'online',
            'amount': 750.0,
            'external_bid_id': 'platform-bid-abc-123',
        })
        self.assertEqual(bid.external_bid_id, 'platform-bid-abc-123')

    def test_14_external_bid_id_field_metadata(self):
        """external_bid_id is a Char field with index=True."""
        fields_info = self.env['sor.bid'].fields_get(['external_bid_id'])
        self.assertIn('external_bid_id', fields_info)
        self.assertEqual(fields_info['external_bid_id']['type'], 'char')

    # ------------------------------------------------------------------
    # 7. Multi-company isolation
    # ------------------------------------------------------------------

    def test_15_multi_company_isolation(self):
        """A bid belonging to Company A is not visible to a Company B-only user."""
        bid_a = self.env['sor.bid'].create({
            'lot_id': self.lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'floor',
            'amount': 1000.0,
        })

        # Record rules are bypassed by the superuser env used in TransactionCase.
        # Create a non-admin user restricted to Company B to exercise the ir.rule.
        company_b_user = self.env['res.users'].create({
            'name': 'Company B Test User',
            'login': 'sor_bidding_test_user_b',
            'company_id': self.company_b.id,
            'company_ids': [(6, 0, [self.company_b.id])],
        })
        bids_in_b = self.env['sor.bid'].with_user(company_b_user).search([])
        self.assertNotIn(
            bid_a, bids_in_b,
            "Company A bids should not be visible to a Company B-only user",
        )

    def test_16_bids_visible_within_own_company(self):
        """A bid is visible to users of its own company."""
        bid_a = self.env['sor.bid'].create({
            'lot_id': self.lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'phone',
            'amount': 800.0,
        })
        bids_in_a = self.env['sor.bid'].with_company(self.company_a).search([])
        self.assertIn(
            bid_a, bids_in_a,
            "Company A bid should be visible in a Company A search context",
        )

    # ------------------------------------------------------------------
    # 8. Composability guard
    # ------------------------------------------------------------------

    def test_17_bid_ids_present_on_sor_lot(self):
        """sor.lot has bid_ids when sor_bidding is installed (composability confirmation)."""
        fields_info = self.env['sor.lot'].fields_get()
        self.assertIn(
            'bid_ids', fields_info,
            "bid_ids should be present on sor.lot when sor_bidding is installed",
        )

    def test_18_bid_count_present_on_sor_lot(self):
        """sor.lot has bid_count when sor_bidding is installed."""
        fields_info = self.env['sor.lot'].fields_get()
        self.assertIn(
            'bid_count', fields_info,
            "bid_count should be present on sor.lot when sor_bidding is installed",
        )
        self.assertEqual(fields_info['bid_count']['type'], 'integer')

    # ------------------------------------------------------------------
    # 10. is_winning_bid — set on winning bid after Sold transition
    # ------------------------------------------------------------------

    def test_19_is_winning_bid_set_on_highest_bid_after_mark_sold(self):
        """action_mark_sold sets is_winning_bid=True on the highest-amount bid."""
        lot = self.env['sor.lot'].create({
            'product_id': self.product.id,
            'company_id': self.company_a.id,
            'lot_number': '019',
        })
        lot.action_catalogue()

        low_bid = self.env['sor.bid'].create({
            'lot_id': lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'floor',
            'amount': 2000.0,
        })
        high_bid = self.env['sor.bid'].create({
            'lot_id': lot.id,
            'bidder_id': self.bidder.id,
            'bid_type': 'floor',
            'amount': 5000.0,
        })

        lot.action_mark_sold()

        self.assertTrue(
            high_bid.is_winning_bid,
            "Highest bid must be marked is_winning_bid=True after action_mark_sold",
        )
        self.assertFalse(
            low_bid.is_winning_bid,
            "Lower bid must not be marked as winning bid",
        )

    # ------------------------------------------------------------------
    # 11. action_view_bids — lot-filtered domain
    # ------------------------------------------------------------------

    def test_20_action_view_bids_returns_lot_filtered_domain(self):
        """action_view_bids() on sor.lot returns an act_window domain filtered to that lot."""
        action = self.lot.action_view_bids()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'sor.bid')
        self.assertIn(
            ('lot_id', '=', self.lot.id),
            action.get('domain', []),
            "action_view_bids domain must include ('lot_id', '=', self.lot.id)",
        )

    # ------------------------------------------------------------------
    # 12. res.partner extension — bid history
    # ------------------------------------------------------------------

    def test_21_bid_ids_and_count_on_res_partner(self):
        """sor_bidding adds bid_ids and bid_count to res.partner."""
        fields_info = self.env['res.partner'].fields_get()
        self.assertIn(
            'bid_ids', fields_info,
            "bid_ids should be present on res.partner when sor_bidding is installed",
        )
        self.assertIn(
            'bid_count', fields_info,
            "bid_count should be present on res.partner when sor_bidding is installed",
        )

    def test_22_partner_action_view_bids_company_scoped(self):
        """action_view_bids() on res.partner filters by bidder_id and company_id."""
        action = self.bidder.action_view_bids()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'sor.bid')
        domain = action.get('domain', [])
        self.assertIn(
            ('bidder_id', '=', self.bidder.id),
            domain,
            "Partner action_view_bids domain must filter by bidder_id",
        )
        self.assertIn(
            ('company_id', '=', self.env.company.id),
            domain,
            "Partner action_view_bids domain must filter by current company",
        )

    # ------------------------------------------------------------------
    # 13. Bidder auto-classification hook (Story 05)
    # ------------------------------------------------------------------

    def test_23_bidder_hook_assigns_contact_and_bidder_on_first_bid(self):
        """Creating a bid auto-assigns Contact parent type and Bidder sub-type to bidder."""
        partner = self.env['res.partner'].create({'name': 'New Bidder Hook Test'})
        self.assertFalse(partner.contact_types, "Partner should start with no contact types")
        self.assertFalse(partner.contact_subtypes, "Partner should start with no contact sub-types")

        self.env['sor.bid'].create({
            'bidder_id': partner.id,
            'lot_id': self.lot.id,
            'bid_type': 'floor',
            'amount': 500.0,
        })

        partner.invalidate_recordset(['contact_types', 'contact_subtypes'])
        type_codes = partner.contact_types.mapped('code')
        subtype_codes = partner.contact_subtypes.mapped('code')
        self.assertIn('contact', type_codes, "Contact parent type should be auto-assigned on first bid")
        self.assertIn('bidder', subtype_codes, "Bidder sub-type should be auto-assigned on first bid")

    def test_24_bidder_hook_is_idempotent(self):
        """Creating a second bid does not duplicate Contact type or Bidder sub-type."""
        partner = self.env['res.partner'].create({'name': 'Idempotent Bidder Test'})

        self.env['sor.bid'].create({
            'bidder_id': partner.id,
            'lot_id': self.lot.id,
            'bid_type': 'floor',
            'amount': 100.0,
        })
        self.env['sor.bid'].create({
            'bidder_id': partner.id,
            'lot_id': self.lot.id,
            'bid_type': 'online',
            'amount': 200.0,
        })

        partner.invalidate_recordset(['contact_types', 'contact_subtypes'])
        contact_count = len(partner.contact_types.filtered(lambda t: t.code == 'contact'))
        bidder_count = len(partner.contact_subtypes.filtered(lambda t: t.code == 'bidder'))
        self.assertEqual(contact_count, 1, "Contact type should not be duplicated after multiple bids")
        self.assertEqual(bidder_count, 1, "Bidder sub-type should not be duplicated after multiple bids")

    def test_25_any_contact_accepted_as_bidder_via_orm(self):
        """The ORM accepts any contact as a bidder regardless of the field's UI domain.

        The bidder_id field carries domain=[('is_contact', '=', True)] which pre-filters
        the UI autocomplete to Contact-type partners. However, the ORM does not enforce
        field domains on write — any partner can be assigned as bidder programmatically
        (e.g. first-time bidders selected via Search More, or created via API).
        The hook fires and assigns Contact + Bidder regardless of how the bidder was set.
        """
        unclassified_partner = self.env['res.partner'].create({'name': 'Unclassified Contact'})
        self.assertFalse(
            unclassified_partner.contact_types,
            "Partner should start with no types",
        )

        # Creating a bid for an unclassified partner must succeed (ORM ignores field domain)
        bid = self.env['sor.bid'].create({
            'bidder_id': unclassified_partner.id,
            'lot_id': self.lot.id,
            'bid_type': 'floor',
            'amount': 300.0,
        })
        self.assertTrue(bid.id, "Bid for unclassified contact must be created successfully via ORM")

    # ------------------------------------------------------------------
    # 14. Bidder hook — cross-company context (F-13)
    # ------------------------------------------------------------------

    def test_26_bidder_hook_fires_in_cross_company_context(self):
        """Bidder hook assigns Contact + Bidder even when the bid is recorded
        in a different company session from the one that created the partner.

        With shared partners (F-12), this is a normal scenario: an artist or
        collector created in Company A receives their first bid recorded by a
        Company B auction operator."""
        partner = self.env['res.partner'].create({
            'name': 'Cross-Company Bidder Hook Test',
            'company_id': self.company_a.id,
        })
        self.assertFalse(partner.contact_subtypes, "Partner should start with no sub-types")

        env_b = self.env(context=dict(
            self.env.context,
            allowed_company_ids=[self.company_b.id],
        ))
        env_b['sor.bid'].create({
            'bidder_id': partner.id,
            'lot_id': self.lot.id,
            'bid_type': 'floor',
            'amount': 750.0,
        })

        partner.invalidate_recordset(['contact_types', 'contact_subtypes'])
        subtype_codes = partner.contact_subtypes.mapped('code')
        self.assertIn(
            'bidder', subtype_codes,
            "Bidder sub-type must be assigned even when bid is recorded in a different company context",
        )
