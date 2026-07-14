from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorLottingContactRoles(TransactionCase):
    """Tests for the sor_lotting_contact_roles bridge module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Test Consignor'})
        # Create a dedicated test product. Use standard paradigm explicitly to
        # avoid artwork-specific validation (Creator required) when
        # sor_asset_paradigm_artwork is installed in the test environment.
        create_vals = {
            'name': 'Test Storable Product (sor_lotting_contact_roles)',
            'type': 'consu',
            'is_storable': True,
        }
        if 'asset_paradigm' in cls.env['product.template']._fields:
            create_vals['asset_paradigm'] = 'standard'
        # Prevent sor_artwork's default_get from setting product_type='artwork',
        # which would trigger the Creator required constraint.
        if 'product_type' in cls.env['product.template']._fields:
            create_vals['product_type'] = False
        cls.product = cls.env['product.template'].sudo().create(create_vals)

    def test_module_installs(self):
        """sor_lotting_contact_roles model extensions are accessible."""
        self.assertIn('consigned_lot_count', self.env['res.partner']._fields)

    def test_consigned_lot_count_zero_for_new_partner(self):
        """A partner with no consigned lots has consigned_lot_count = 0."""
        partner = self.env['res.partner'].create({'name': 'New Partner No Lots'})
        self.assertEqual(partner.consigned_lot_count, 0)

    def test_consigned_lot_count_increments_on_lot_create(self):
        """Creating a lot with consignor_id increments the partner's count."""
        initial = self.partner.consigned_lot_count
        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'consignor_id': self.partner.id,
        })
        # store=False + @api.depends() (empty) means no automatic cache invalidation.
        # Flush and invalidate before re-reading so the count reflects the new DB state.
        self.env.flush_all()
        self.partner.invalidate_recordset(['consigned_lot_count'])
        self.assertEqual(self.partner.consigned_lot_count, initial + 1)

    def test_consignor_subtype_assigned_on_lot_create(self):
        """Creating a lot with consignor_id assigns the Consignor sub-type."""
        consignor_subtype = self.env['sor.contact.type'].search(
            [('code', '=', 'consignor')], limit=1,
        )
        if not consignor_subtype:
            self.skipTest('Consignor contact type not configured')
        partner = self.env['res.partner'].create({'name': 'Sub-type Test Consignor'})
        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'consignor_id': partner.id,
        })
        self.assertIn(consignor_subtype, partner.contact_subtypes)

    def test_consignor_subtype_assigned_on_lot_write(self):
        """Setting consignor_id via write assigns the Consignor sub-type."""
        consignor_subtype = self.env['sor.contact.type'].search(
            [('code', '=', 'consignor')], limit=1,
        )
        if not consignor_subtype:
            self.skipTest('Consignor contact type not configured')
        partner = self.env['res.partner'].create({'name': 'Write Sub-type Consignor'})
        lot = self.env['sor.lot'].create({'product_id': self.product.id})
        lot.write({'consignor_id': partner.id})
        self.assertIn(consignor_subtype, partner.contact_subtypes)

    def test_buyer_subtype_assigned_on_lot_create(self):
        """Creating a lot with buyer_id assigns the Buyer sub-type (BUG-U17)."""
        buyer_subtype = self.env['sor.contact.type'].search(
            [('code', '=', 'buyer')], limit=1,
        )
        if not buyer_subtype:
            self.skipTest('Buyer contact type not configured')
        partner = self.env['res.partner'].create({'name': 'Sub-type Test Buyer'})
        self.env['sor.lot'].create({
            'product_id': self.product.id,
            'buyer_id': partner.id,
        })
        self.assertIn(buyer_subtype, partner.contact_subtypes)

    def test_buyer_subtype_assigned_on_lot_write(self):
        """Setting buyer_id via write assigns the Buyer sub-type (BUG-U17)."""
        buyer_subtype = self.env['sor.contact.type'].search(
            [('code', '=', 'buyer')], limit=1,
        )
        if not buyer_subtype:
            self.skipTest('Buyer contact type not configured')
        partner = self.env['res.partner'].create({'name': 'Write Sub-type Buyer'})
        lot = self.env['sor.lot'].create({'product_id': self.product.id})
        lot.write({'buyer_id': partner.id})
        self.assertIn(buyer_subtype, partner.contact_subtypes)
