from odoo.tests import TransactionCase, tagged

from odoo.addons.sor_commercial_auction_house import hooks


@tagged('post_install', '-at_install')
class TestSorCommercialAuctionHouse(TransactionCase):
    """
    Automated tests for sor_commercial_auction_house.

    Covers:
    - Module installs and key models accessible
    - post_init_hook seeds fee records per company
    - Break-even formula: reserve / (1 - commission/100)
    - default_get cascade: company default and consignor override
    - is_commercial_auction computed field behaviour
    - Suppression rules installed for auction_house business model
    - Composability: fee fields are owned by this bridge

    Run with:
        docker exec odoo-app python3 odoo-bin \\
          --addons-path=/mnt/extra-addons,/app/odoo/addons \\
          --db_host=postgres --db_port=5432 --db_user=odoo --db_password=admin \\
          -d odoo -u sor_commercial_auction_house \\
          --test-tags=post_install --stop-after-init
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Use the main test company and ensure it is set to auction_house
        cls.company = cls.env.company
        cls.company.business_model = 'auction_house'

        # Locate a storable product to use as the lot product
        cls.product = cls.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not cls.product:
            cls.product = cls.env['product.template'].sudo().create({
                'name': 'Test Storable Product — CAH',
                'type': 'consu',
                'is_storable': True,
            })

        # Ensure the company has fee records seeded (post_init_hook may have run,
        # or the company was created before this bridge installed — ensure_* is safe to call)
        hooks._ensure_fee_defaults(cls.env, cls.company)
        hooks._ensure_buyers_premium_tier(cls.env, cls.company)

        # Locate the company's fee defaults
        cls.sellers_commission_fee = cls.env['sor.fee.default'].search([
            ('company_id', '=', cls.company.id),
            ('fee_type', '=', 'sellers_commission'),
        ], limit=1)
        cls.withdrawal_fee = cls.env['sor.fee.default'].search([
            ('company_id', '=', cls.company.id),
            ('fee_type', '=', 'withdrawal_fee'),
        ], limit=1)
        cls.premium_tier = cls.env['sor.buyers.premium.tier'].search([
            ('company_id', '=', cls.company.id),
        ], order='sequence asc', limit=1)

        # Consignor partner with a custom default_sellers_commission_pct
        cls.consignor = cls.env['res.partner'].create({
            'name': 'Test Consignor — CAH',
            'default_sellers_commission_pct': 15.0,
        })

    def _make_lot(self, **kwargs):
        """Helper: create a sor.lot with minimum required fields."""
        vals = {
            'product_id': self.product.id,
            'company_id': self.company.id,
        }
        vals.update(kwargs)
        return self.env['sor.lot'].create(vals)

    # ------------------------------------------------------------------
    # 1. Module installs
    # ------------------------------------------------------------------

    def test_01_module_installs_fee_default_model(self):
        """sor.fee.default model is accessible from the environment."""
        self.assertIn('sor.fee.default', self.env)

    def test_02_module_installs_buyers_premium_tier_model(self):
        """sor.buyers.premium.tier model is accessible from the environment."""
        self.assertIn('sor.buyers.premium.tier', self.env)

    def test_03_module_installs_bridge_declared(self):
        """sor_commercial_auction_house is installed and declares correct parents."""
        bridge = self.env['ir.module.module'].search([
            ('name', '=', 'sor_commercial_auction_house'),
        ], limit=1)
        self.assertTrue(bridge, "Bridge module must be findable in ir.module.module")
        self.assertEqual(bridge.state, 'installed')

        dep_names = self.env['ir.module.module.dependency'].search([
            ('module_id', '=', bridge.id),
        ]).mapped('name')
        self.assertIn('sor_business_model', dep_names)
        self.assertIn('sor_events_auction', dep_names)

    # ------------------------------------------------------------------
    # 2. post_init_hook seeds fee records
    # ------------------------------------------------------------------

    def test_04_post_init_hook_seeds_sellers_commission(self):
        """post_init_hook creates a sellers_commission fee record for the company."""
        self.assertTrue(
            self.sellers_commission_fee,
            "A sellers_commission sor.fee.default must exist for the main company",
        )
        self.assertEqual(self.sellers_commission_fee.company_id, self.company)
        self.assertEqual(self.sellers_commission_fee.fee_type, 'sellers_commission')

    def test_05_post_init_hook_seeds_withdrawal_fee(self):
        """post_init_hook creates a withdrawal_fee record for the company."""
        self.assertTrue(
            self.withdrawal_fee,
            "A withdrawal_fee sor.fee.default must exist for the main company",
        )
        self.assertEqual(self.withdrawal_fee.company_id, self.company)
        self.assertEqual(self.withdrawal_fee.fee_type, 'withdrawal_fee')

    def test_06_post_init_hook_seeds_buyers_premium_tier(self):
        """post_init_hook creates at least one buyers_premium_tier for the company."""
        self.assertTrue(
            self.premium_tier,
            "At least one sor.buyers.premium.tier must exist for the main company",
        )
        self.assertEqual(self.premium_tier.company_id, self.company)

    def test_07_new_company_gets_fee_records_on_create(self):
        """Creating a new company via res.company.create seeds fee and tier records."""
        new_company = self.env['res.company'].create({'name': 'New Auction House — CAH Test'})
        new_company.business_model = 'auction_house'

        fee_count = self.env['sor.fee.default'].search_count([
            ('company_id', '=', new_company.id),
        ])
        tier_count = self.env['sor.buyers.premium.tier'].search_count([
            ('company_id', '=', new_company.id),
        ])
        self.assertEqual(fee_count, 2, "Two fee defaults (sellers_commission + withdrawal_fee)")
        self.assertEqual(tier_count, 1, "One buyers_premium_tier seeded for new company")

    # ------------------------------------------------------------------
    # 3. Break-even formula
    # ------------------------------------------------------------------

    def test_08_break_even_with_commission(self):
        """break_even_value = reserve / (1 - commission/100) when commission > 0."""
        # Set 20% seller's commission on the fee default
        self.sellers_commission_fee.rate_pct = 20.0
        lot = self._make_lot(
            reserve_price=8000.0,
            sellers_commission_pct=20.0,
        )
        lot.invalidate_recordset(['break_even_value'])
        # 8000 / (1 - 0.20) = 10000.0
        self.assertAlmostEqual(lot.break_even_value, 10000.0, places=2)

    def test_09_break_even_zero_commission_falls_back_to_reserve(self):
        """break_even_value falls back to reserve_price when commission is 0%."""
        lot = self._make_lot(
            reserve_price=5000.0,
            sellers_commission_pct=0.0,
        )
        lot.invalidate_recordset(['break_even_value'])
        self.assertAlmostEqual(lot.break_even_value, 5000.0, places=2)

    def test_10_break_even_100_commission_falls_back_to_reserve(self):
        """break_even_value falls back to reserve_price when commission is 100% (invalid)."""
        lot = self._make_lot(
            reserve_price=3000.0,
            sellers_commission_pct=100.0,
        )
        lot.invalidate_recordset(['break_even_value'])
        self.assertAlmostEqual(lot.break_even_value, 3000.0, places=2)

    def test_11_break_even_recomputes_on_commission_change(self):
        """Changing sellers_commission_pct on a lot updates break_even_value."""
        lot = self._make_lot(
            reserve_price=10000.0,
            sellers_commission_pct=0.0,
        )
        lot.invalidate_recordset(['break_even_value'])
        self.assertAlmostEqual(lot.break_even_value, 10000.0, places=2)

        lot.sellers_commission_pct = 10.0
        lot.invalidate_recordset(['break_even_value'])
        # 10000 / (1 - 0.10) ≈ 11111.11
        self.assertAlmostEqual(lot.break_even_value, 10000.0 / 0.90, places=2)

    # ------------------------------------------------------------------
    # 4. default_get cascade — company default
    # ------------------------------------------------------------------

    def test_12_default_get_cascades_from_company_fee_schedule(self):
        """default_get pulls sellers_commission from company fee schedule when no consignor."""
        self.sellers_commission_fee.rate_pct = 12.0
        self.withdrawal_fee.rate_pct = 5.0
        self.premium_tier.rate_pct = 18.0

        defaults = self.env['sor.lot'].with_company(self.company).default_get([
            'sellers_commission_pct',
            'withdrawal_fee_pct',
            'buyers_premium_pct',
        ])

        self.assertEqual(
            defaults.get('sellers_commission_pct'), 12.0,
            "sellers_commission_pct must default from company fee schedule",
        )
        self.assertEqual(
            defaults.get('withdrawal_fee_pct'), 5.0,
            "withdrawal_fee_pct must default from company fee schedule",
        )
        self.assertEqual(
            defaults.get('buyers_premium_pct'), 18.0,
            "buyers_premium_pct must default from first buyers premium tier",
        )

    # ------------------------------------------------------------------
    # 5. default_get cascade — consignor override
    # ------------------------------------------------------------------

    def test_13_default_get_always_uses_company_default(self):
        """default_get always returns company fee schedule — consignor cascade removed (fix #22)."""
        self.sellers_commission_fee.rate_pct = 10.0

        defaults = self.env['sor.lot'].with_company(self.company).default_get([
            'sellers_commission_pct',
        ])
        self.assertEqual(
            defaults.get('sellers_commission_pct'), 10.0,
            "Company fee schedule must be used when no consignor cascade exists",
        )

        # Even if default_consignor_id is in context (from a partner action),
        # default_get no longer reads the consignor rate — company default is always used.
        defaults_with_ctx = self.env['sor.lot'].with_company(self.company).with_context(
            default_consignor_id=self.consignor.id,
        ).default_get(['sellers_commission_pct'])
        self.assertEqual(
            defaults_with_ctx.get('sellers_commission_pct'), 10.0,
            "Company default must be returned even when consignor context is present",
        )

    def test_14_default_sellers_commission_pct_field_on_partner(self):
        """default_sellers_commission_pct is stored on res.partner and readable."""
        partner = self.env['res.partner'].create({
            'name': 'Test Seller Partner — CAH',
            'default_sellers_commission_pct': 12.5,
        })
        self.assertAlmostEqual(
            partner.default_sellers_commission_pct, 12.5,
            places=2,
            msg="default_sellers_commission_pct must be stored and readable on res.partner",
        )

    # ------------------------------------------------------------------
    # 6. Per-lot override independence
    # ------------------------------------------------------------------

    def test_15_per_lot_override_does_not_affect_company_schedule(self):
        """Overriding fee fields on a lot does not change the company fee schedule."""
        self.sellers_commission_fee.rate_pct = 10.0
        lot = self._make_lot(
            sellers_commission_pct=25.0,
            reserve_price=4000.0,
        )
        # Company schedule must be unchanged
        self.sellers_commission_fee.invalidate_recordset(['rate_pct'])
        self.assertEqual(
            self.sellers_commission_fee.rate_pct, 10.0,
            "Overriding commission on a lot must not change the company fee schedule",
        )
        # The lot's break-even uses the lot's own rate (25%)
        lot.invalidate_recordset(['break_even_value'])
        self.assertAlmostEqual(lot.break_even_value, 4000.0 / 0.75, places=2)

    def test_16_per_lot_override_does_not_affect_other_lots(self):
        """Overriding fees on one lot does not affect another lot's values."""
        self.sellers_commission_fee.rate_pct = 10.0
        lot_a = self._make_lot(reserve_price=5000.0)
        lot_b = self._make_lot(reserve_price=5000.0)
        # Override only lot_a
        lot_a.sellers_commission_pct = 30.0
        lot_a.invalidate_recordset(['break_even_value'])
        lot_b.invalidate_recordset(['break_even_value'])
        # lot_b retains its own commission; break-even should not equal lot_a's
        self.assertNotAlmostEqual(
            lot_a.break_even_value, lot_b.break_even_value, places=2,
            msg="Per-lot override must not propagate to other lots",
        )

    # ------------------------------------------------------------------
    # 7. is_commercial_auction computed field
    # ------------------------------------------------------------------

    def test_17_is_commercial_auction_true_when_auction_is_commercial(self):
        """is_commercial_auction is True when lot's auction.is_commercial is True."""
        auction = self.env['sor.event'].create({
            'name': 'Commercial Auction — CAH Test',
            'event_type': 'auction',
            'is_commercial': True,
            'date_start': '2026-05-01 10:00:00',
            'company_id': self.company.id,
        })
        lot = self._make_lot(auction_id=auction.id)
        lot.invalidate_recordset(['is_commercial_auction'])
        self.assertTrue(lot.is_commercial_auction)

    def test_18_is_commercial_auction_false_when_auction_is_not_commercial(self):
        """is_commercial_auction is False when lot's auction.is_commercial is False."""
        auction = self.env['sor.event'].create({
            'name': 'Non-Commercial Auction — CAH Test',
            'event_type': 'auction',
            'is_commercial': False,
            'date_start': '2026-10-01 10:00:00',
            'company_id': self.company.id,
        })
        lot = self._make_lot(auction_id=auction.id)
        lot.invalidate_recordset(['is_commercial_auction'])
        self.assertFalse(lot.is_commercial_auction)

    def test_19_is_commercial_auction_reflects_company_model_when_no_auction(self):
        """is_commercial_auction reflects company.business_model when no auction is set."""
        self.company.business_model = 'auction_house'
        lot = self._make_lot()
        lot.invalidate_recordset(['is_commercial_auction'])
        self.assertTrue(
            lot.is_commercial_auction,
            "Lot with no auction must use company business_model to determine is_commercial_auction",
        )

        # Switch to a non-auction-house company model
        self.company.business_model = 'non_commercial'
        lot.invalidate_recordset(['is_commercial_auction'])
        self.assertFalse(lot.is_commercial_auction)

        # Restore for other tests
        self.company.business_model = 'auction_house'

    # ------------------------------------------------------------------
    # 8. Suppression rules installed for auction_house
    # ------------------------------------------------------------------

    def test_20_suppression_rules_exist_for_auction_house(self):
        """Four sor.business.model.rule records exist for auction_house after install."""
        expected_keys = {'can_be_sold', 'sale_price_field', 'sales_tab', 'sale_price_tab'}
        rules = self.env['sor.business.model.rule'].with_context(active_test=False).search([
            ('business_model', '=', 'auction_house'),
        ])
        installed_keys = set(rules.mapped('field_key'))
        for key in expected_keys:
            self.assertIn(
                key, installed_keys,
                f"Suppression rule for '{key}' must be installed for auction_house",
            )

    def test_21_suppression_rules_are_active_by_default(self):
        """All four auction_house suppression rules are active=True after install."""
        rules = self.env['sor.business.model.rule'].search([
            ('business_model', '=', 'auction_house'),
        ])
        self.assertEqual(len(rules), 4, "Exactly four active suppression rules for auction_house")
        for rule in rules:
            self.assertTrue(rule.active, f"Rule '{rule.field_key}' must be active by default")

    # ------------------------------------------------------------------
    # 9. Multi-company isolation of fee records
    # ------------------------------------------------------------------

    def test_22_fee_records_are_company_scoped(self):
        """sor.fee.default records are isolated per company."""
        company_b = self.env['res.company'].create({'name': 'Company B — CAH Test'})
        company_b.business_model = 'auction_house'

        # Ensure company B has its own fee defaults
        hooks._ensure_fee_defaults(self.env, company_b)

        company_b_fees = self.env['sor.fee.default'].search([
            ('company_id', '=', company_b.id),
        ])

        # Modify company B's rate; main company must not be affected
        if company_b_fees:
            company_b_fees[0].rate_pct = 99.0
            self.sellers_commission_fee.invalidate_recordset(['rate_pct'])
            self.assertNotEqual(
                self.sellers_commission_fee.rate_pct, 99.0,
                "Company B fee record must not affect main company fee record",
            )

    # ------------------------------------------------------------------
    # 10. Composability — fee fields owned by this bridge
    # ------------------------------------------------------------------

    def test_23_composability_fee_fields_on_sor_lot(self):
        """Fee fields added by the bridge are present on sor.lot when bridge installed."""
        expected_fields = {
            'sellers_commission_pct',
            'withdrawal_fee_pct',
            'buyers_premium_pct',
            'is_commercial_auction',
        }
        lot_fields = self.env['sor.lot']._fields
        for field_name in expected_fields:
            self.assertIn(
                field_name, lot_fields,
                f"Field '{field_name}' must be present on sor.lot when bridge is installed",
            )

    def test_24_composability_is_commercial_on_sor_event(self):
        """is_commercial field is present on sor.event when bridge installed."""
        self.assertIn('is_commercial', self.env['sor.event']._fields)

    def test_25_composability_default_sellers_commission_pct_on_res_partner(self):
        """default_sellers_commission_pct is present on res.partner when bridge installed."""
        self.assertIn('default_sellers_commission_pct', self.env['res.partner']._fields)

    def test_26_composability_fee_fields_owned_by_bridge(self):
        """sellers_commission_pct is attributed to sor_commercial_auction_house."""
        for field_name in ('sellers_commission_pct',):
            field_rec = self.env['ir.model.fields'].search([
                ('model', '=', 'sor.lot'),
                ('name', '=', field_name),
            ], limit=1)
            self.assertTrue(field_rec, f"ir.model.fields entry must exist for sor.lot.{field_name}")
            self.assertIn(
                'sor_commercial_auction_house',
                field_rec.modules,
                f"sor.lot.{field_name} must be attributed to sor_commercial_auction_house",
            )
