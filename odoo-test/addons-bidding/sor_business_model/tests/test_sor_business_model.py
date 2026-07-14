from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorBusinessModel(TransactionCase):
    """
    Tests for sor_business_model: selection values, default, multi-company
    isolation, effective_business_model computed field, and is_field_suppressed
    rule evaluation.

    Covers Sprint 07 Story 01 confirmed ACs (auction_house,
    primary_market_gallery, secondary_market_gallery) plus the base suppression
    mechanism that all four values share.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Use the main company already present in the test database.
        cls.company = cls.env.company
        # Reset to a known baseline so tests are order-independent.
        cls.company.business_model = 'non_commercial'

        # Locate an existing storable product rather than creating one, to
        # avoid having to satisfy sor_artwork required fields (creator_id etc.)
        # that are present in the test DB.
        cls.product = cls.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not cls.product:
            # Fallback: find any product template at all.
            cls.product = cls.env['product.template'].search([], limit=1)

    # ------------------------------------------------------------------
    # 1. Module installs
    # ------------------------------------------------------------------

    def test_module_installs(self):
        """sor.business.model.rule model is accessible from the environment."""
        Rule = self.env['sor.business.model.rule']
        self.assertIsNotNone(Rule, "sor.business.model.rule must be accessible")

    # ------------------------------------------------------------------
    # 2-6. Selection values
    # ------------------------------------------------------------------

    def test_all_four_selection_values_accepted(self):
        """All four business_model values can be written to a company without error."""
        for value in ('non_commercial', 'primary_market_gallery',
                      'secondary_market_gallery', 'auction_house'):
            self.company.business_model = value
            self.assertEqual(
                self.company.business_model, value,
                f"Expected business_model to be '{value}' after write",
            )

    def test_default_is_non_commercial(self):
        """A freshly created company defaults to 'non_commercial'."""
        company = self.env['res.company'].create({'name': 'Default Test Co'})
        self.assertEqual(
            company.business_model, 'non_commercial',
            "New company should default to 'non_commercial'",
        )

    def test_auction_house_value_saves_correctly(self):
        """'auction_house' round-trips through the ORM without corruption."""
        self.company.business_model = 'auction_house'
        self.env.flush_all()
        self.company.invalidate_recordset(['business_model'])
        self.assertEqual(self.company.business_model, 'auction_house')

    def test_primary_market_gallery_value_saves_correctly(self):
        """'primary_market_gallery' round-trips through the ORM without corruption."""
        self.company.business_model = 'primary_market_gallery'
        self.env.flush_all()
        self.company.invalidate_recordset(['business_model'])
        self.assertEqual(self.company.business_model, 'primary_market_gallery')

    def test_secondary_market_gallery_value_saves_correctly(self):
        """'secondary_market_gallery' round-trips through the ORM without corruption."""
        self.company.business_model = 'secondary_market_gallery'
        self.env.flush_all()
        self.company.invalidate_recordset(['business_model'])
        self.assertEqual(self.company.business_model, 'secondary_market_gallery')

    # ------------------------------------------------------------------
    # 7. Multi-company isolation
    # ------------------------------------------------------------------

    def test_multi_company_independent_values(self):
        """
        Setting business_model on a second company does not affect the first.
        Each company holds its own independent value.
        """
        company2 = self.env['res.company'].create({'name': 'Second Test Co'})
        self.company.business_model = 'non_commercial'
        company2.business_model = 'auction_house'

        self.env.flush_all()
        self.company.invalidate_recordset(['business_model'])
        company2.invalidate_recordset(['business_model'])

        self.assertEqual(
            self.company.business_model, 'non_commercial',
            "First company should be unaffected by the second company's value",
        )
        self.assertEqual(
            company2.business_model, 'auction_house',
            "Second company should hold 'auction_house'",
        )

    # ------------------------------------------------------------------
    # 8. effective_business_model computed field
    # ------------------------------------------------------------------

    def test_effective_business_model_returns_company_value(self):
        """
        effective_business_model on a product reflects the active company's
        business_model value when accessed with that company in context.
        """
        if not self.product:
            self.skipTest("No product.template records available in test DB")

        self.company.business_model = 'auction_house'
        product_in_context = self.product.with_company(self.company)
        self.assertEqual(
            product_in_context.effective_business_model, 'auction_house',
            "effective_business_model should mirror the company's business_model",
        )

    # ------------------------------------------------------------------
    # 9-11. is_field_suppressed rule evaluation
    # ------------------------------------------------------------------

    def test_is_field_suppressed_true_with_active_rule(self):
        """
        is_field_suppressed returns True when an active rule exists for the
        current company's business_model + field_key combination.

        Uses 'auction_house' to avoid interference from sor_business_model_non_commercial
        which installs active rules for 'non_commercial' + 'can_be_sold'.
        """
        self.company.business_model = 'auction_house'
        # Clear any stray rules first.
        self.env['sor.business.model.rule'].with_context(active_test=False).search([
            ('business_model', '=', 'auction_house'),
            ('field_key', '=', 'can_be_sold'),
        ]).unlink()
        rule = self.env['sor.business.model.rule'].create({
            'business_model': 'auction_house',
            'field_key': 'can_be_sold',
            'active': True,
        })
        try:
            product_in_context = self.product.with_company(self.company) if self.product \
                else self.env['product.template'].with_company(self.company)
            if not product_in_context:
                self.skipTest("No product.template records available in test DB")
            self.assertTrue(
                product_in_context.is_field_suppressed('can_be_sold'),
                "is_field_suppressed should return True when an active rule exists",
            )
        finally:
            rule.unlink()

    def test_is_field_suppressed_false_with_inactive_rule(self):
        """
        is_field_suppressed returns False when the matching rule exists but has
        active=False (i.e. the Suppressed checkbox is unchecked).

        Uses 'auction_house' to avoid interference from sor_business_model_non_commercial
        which installs active rules for 'non_commercial' + 'can_be_sold'.
        """
        self.company.business_model = 'auction_house'
        # Clear any stray rules first.
        self.env['sor.business.model.rule'].with_context(active_test=False).search([
            ('business_model', '=', 'auction_house'),
            ('field_key', '=', 'can_be_sold'),
        ]).unlink()
        rule = self.env['sor.business.model.rule'].create({
            'business_model': 'auction_house',
            'field_key': 'can_be_sold',
            'active': False,
        })
        try:
            product_in_context = self.product.with_company(self.company) if self.product \
                else self.env['product.template'].with_company(self.company)
            if not product_in_context:
                self.skipTest("No product.template records available in test DB")
            self.assertFalse(
                product_in_context.is_field_suppressed('can_be_sold'),
                "is_field_suppressed should return False when the rule is inactive",
            )
        finally:
            rule.with_context(active_test=False).unlink()

    def test_is_field_suppressed_false_with_no_rules(self):
        """
        is_field_suppressed returns False when no rule exists for the current
        company's business_model + field_key combination.
        """
        self.company.business_model = 'auction_house'
        # Ensure no stray rule exists for this combination.
        self.env['sor.business.model.rule'].with_context(active_test=False).search([
            ('business_model', '=', 'auction_house'),
            ('field_key', '=', 'can_be_sold'),
        ]).unlink()

        product_in_context = self.product.with_company(self.company) if self.product \
            else self.env['product.template'].with_company(self.company)
        if not product_in_context:
            self.skipTest("No product.template records available in test DB")
        self.assertFalse(
            product_in_context.is_field_suppressed('can_be_sold'),
            "is_field_suppressed should return False when no rule exists",
        )
