import re

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
    # 4. Lot creation cascade — company default
    # ------------------------------------------------------------------

    def test_12_lot_creation_uses_company_fee_schedule_for_commission(self):
        """A new lot's sellers_commission_pct is computed from company fee schedule.

        sellers_commission_pct is a computed+inverse field (BUG-S04-F04/F06), so
        default_get does not return it.  The computed value on a freshly-created
        lot is the authoritative test for the company-schedule cascade.

        withdrawal_fee_pct and buyers_premium_pct are still plain Float fields
        populated via default_get; those remain tested via default_get.
        """
        self.sellers_commission_fee.rate_pct = 12.0
        self.withdrawal_fee.rate_pct = 5.0
        self.premium_tier.rate_pct = 18.0

        # sellers_commission_pct: verify via lot creation
        lot = self._make_lot()
        lot.invalidate_recordset(['sellers_commission_pct'])
        self.assertAlmostEqual(
            lot.sellers_commission_pct, 12.0, places=1,
            msg="sellers_commission_pct must be computed from company fee schedule on a new lot",
        )

        # withdrawal_fee_pct and buyers_premium_pct: still via default_get
        defaults = self.env['sor.lot'].with_company(self.company).default_get([
            'withdrawal_fee_pct',
            'buyers_premium_pct',
        ])
        self.assertEqual(
            defaults.get('withdrawal_fee_pct'), 5.0,
            "withdrawal_fee_pct must default from company fee schedule",
        )
        self.assertEqual(
            defaults.get('buyers_premium_pct'), 18.0,
            "buyers_premium_pct must default from first buyers premium tier",
        )

    # ------------------------------------------------------------------
    # 5. Computed commission — company default vs consignor override
    # ------------------------------------------------------------------

    def test_13_sellers_commission_uses_company_default_without_consignor_override(self):
        """sellers_commission_pct uses company rate unless consignor.use_custom_default_commission.

        sellers_commission_pct is a computed+inverse field (BUG-S04-F04/F06).
        The old default_get cascade was removed.  Verify the computed field
        behaviour via lot creation: company default always wins unless the
        consignor explicitly has use_custom_default_commission=True.
        """
        self.sellers_commission_fee.rate_pct = 10.0

        # Lot without consignor — must use company rate
        lot_no_consignor = self._make_lot()
        lot_no_consignor.invalidate_recordset(['sellers_commission_pct'])
        self.assertAlmostEqual(
            lot_no_consignor.sellers_commission_pct, 10.0, places=1,
            msg="Company fee schedule must be used when no consignor is set",
        )

        # Lot with a consignor who does NOT have use_custom_default_commission=True
        # (cls.consignor has default_sellers_commission_pct=15.0 but the toggle is off)
        lot_with_consignor = self._make_lot(consignor_id=self.consignor.id)
        lot_with_consignor.invalidate_recordset(['sellers_commission_pct'])
        self.assertAlmostEqual(
            lot_with_consignor.sellers_commission_pct, 10.0, places=1,
            msg="Company default must be used when consignor.use_custom_default_commission is False",
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

    # ------------------------------------------------------------------
    # 11. Fixed Charge Type registry
    # ------------------------------------------------------------------

    def test_27_fixed_charge_type_model_installed(self):
        """sor.fixed.charge.type model is accessible from the environment."""
        self.assertIn('sor.fixed.charge.type', self.env)

    def test_28_fixed_charge_type_seeded_four_types(self):
        """Four Fixed Charge Types are seeded on install."""
        names = self.env['sor.fixed.charge.type'].search([]).mapped('name')
        for expected in ('Restoration', 'Framing', 'Transportation', 'Installation'):
            self.assertIn(expected, names)

    def test_29_fixed_charge_type_has_no_company_id(self):
        """sor.fixed.charge.type is a global registry — no company_id field."""
        self.assertNotIn('company_id', self.env['sor.fixed.charge.type']._fields)

    def test_30_fixed_charge_type_shared_across_companies(self):
        """The same Fixed Charge Type records are visible regardless of company context."""
        company_b = self.env['res.company'].create({'name': 'Company B — Fixed Charge Test'})
        names_main = self.env['sor.fixed.charge.type'].search([]).mapped('name')
        names_company_b = self.env['sor.fixed.charge.type'].with_company(company_b).search([]).mapped('name')
        self.assertEqual(sorted(names_main), sorted(names_company_b))

    def test_31_fixed_charge_type_archive_excludes_from_default_search(self):
        """Archiving a Fixed Charge Type hides it from default (active_test=True) searches."""
        charge_type = self.env['sor.fixed.charge.type'].create({'name': 'Test Archivable Type'})
        charge_type.active = False
        self.assertNotIn(
            charge_type, self.env['sor.fixed.charge.type'].search([]),
        )
        self.assertIn(
            charge_type,
            self.env['sor.fixed.charge.type'].with_context(active_test=False).search([]),
        )

    # ------------------------------------------------------------------
    # 12. Lot Fixed Charge line model
    # ------------------------------------------------------------------

    def test_32_lot_fixed_charge_model_installed(self):
        """sor.lot.fixed.charge model is accessible from the environment."""
        self.assertIn('sor.lot.fixed.charge', self.env)

    def test_33_lot_fixed_charge_currency_and_company_track_lot(self):
        """currency_id and company_id on a Fixed Charge line mirror the parent lot."""
        lot = self._make_lot()
        charge_type = self.env['sor.fixed.charge.type'].search([('name', '=', 'Restoration')], limit=1)
        charge = self.env['sor.lot.fixed.charge'].create({
            'lot_id': lot.id,
            'charge_type_id': charge_type.id,
            'amount': 50.0,
        })
        self.assertEqual(charge.currency_id, lot.currency_id)
        self.assertEqual(charge.company_id, lot.company_id)

    def test_34_lot_fixed_charge_cascade_delete_with_lot(self):
        """Deleting a lot deletes its Fixed Charge lines (ondelete=cascade)."""
        lot = self._make_lot()
        charge_type = self.env['sor.fixed.charge.type'].search([('name', '=', 'Framing')], limit=1)
        charge = self.env['sor.lot.fixed.charge'].create({
            'lot_id': lot.id,
            'charge_type_id': charge_type.id,
            'amount': 30.0,
        })
        charge_id = charge.id
        lot.unlink()
        self.assertFalse(self.env['sor.lot.fixed.charge'].search([('id', '=', charge_id)]))

    def test_35_fixed_charge_ids_copy_true_carries_over_on_lot_copy(self):
        """Fixed Charges are content of the lot — copy=True carries them to a duplicated lot."""
        lot = self._make_lot()
        charge_type = self.env['sor.fixed.charge.type'].search([('name', '=', 'Transportation')], limit=1)
        self.env['sor.lot.fixed.charge'].create({
            'lot_id': lot.id,
            'charge_type_id': charge_type.id,
            'amount': 20.0,
        })
        copied_lot = lot.copy()
        self.assertEqual(len(copied_lot.fixed_charge_ids), 1)
        self.assertEqual(copied_lot.fixed_charge_ids.charge_type_id, charge_type)

    # ------------------------------------------------------------------
    # 13. Story 02 — Remove Dead Column Name Kwarg (res.company.vat_margin_scheme)
    # ------------------------------------------------------------------

    def test_36_vat_margin_scheme_field_has_no_column_name_kwarg(self):
        """res.company.vat_margin_scheme carries no column_name kwarg (dead parameter removed)."""
        field = self.env['res.company']._fields['vat_margin_scheme']
        self.assertFalse(
            hasattr(field, 'column_name'),
            "vat_margin_scheme must not declare a column_name kwarg",
        )

    def test_37_vat_margin_scheme_read_write_unaffected(self):
        """vat_margin_scheme on res.company still reads/writes correctly after kwarg removal."""
        self.company.vat_margin_scheme = True
        self.assertTrue(self.company.vat_margin_scheme)
        self.company.vat_margin_scheme = False
        self.assertFalse(self.company.vat_margin_scheme)

    # ------------------------------------------------------------------
    # 14. Story 05 — Fees tab / catalogue-content field locking
    # ------------------------------------------------------------------

    def _fees_tab_combined_arch(self):
        return self.env.ref('sor_commercial_auction_house.sor_lot_view_form_fees').get_combined_arch()

    def _field_tag(self, arch, field_name):
        """Return the opening <field name="field_name" .../> tag (self-closed or not) from arch."""
        match = re.search(rf'<field name="{field_name}"[^>]*?/?>', arch)
        self.assertIsNotNone(match, f"<field name=\"{field_name}\"> not found in combined arch")
        return match.group(0)

    def test_38_fees_tab_toggle_fields_never_locked_by_state(self):
        """The two override toggles carry no readonly or invisible expression at all (never lock/disappear)."""
        arch = self._fees_tab_combined_arch()
        for field_name in ('use_custom_vendor_fee', 'use_custom_buyer_premium'):
            tag = self._field_tag(arch, field_name)
            self.assertNotIn('readonly', tag, f"{field_name} must not be readonly-gated")
            self.assertNotIn('invisible', tag, f"{field_name} must not be invisible-gated")

    def test_39_fees_tab_pct_fields_gated_only_by_toggle_not_state(self):
        """Vendor/Buyer Premium % fields are readonly only when their own toggle is off — no state clause."""
        arch = self._fees_tab_combined_arch()
        vendor_tag = self._field_tag(arch, 'sellers_commission_pct')
        self.assertIn('readonly="not use_custom_vendor_fee"', vendor_tag)
        self.assertNotIn('state', vendor_tag)
        premium_tag = self._field_tag(arch, 'buyers_premium_pct')
        self.assertIn('readonly="not use_custom_buyer_premium"', premium_tag)
        self.assertNotIn('state', premium_tag)

    def test_40_withdrawal_fee_pct_never_locked(self):
        """withdrawal_fee_pct carries no readonly attribute at all."""
        arch = self._fees_tab_combined_arch()
        tag = self._field_tag(arch, 'withdrawal_fee_pct')
        self.assertNotIn('readonly', tag)

    def test_41_fixed_charge_ids_not_locked_by_state(self):
        """fixed_charge_ids's own field tag carries no readonly attribute."""
        arch = self._fees_tab_combined_arch()
        tag = self._field_tag(arch, 'fixed_charge_ids')
        self.assertNotIn('readonly', tag)
