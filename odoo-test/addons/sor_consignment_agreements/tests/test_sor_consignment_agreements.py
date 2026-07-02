from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

# ---------------------------------------------------------------------------
# Class 1 — Module install verification
# ---------------------------------------------------------------------------


@tagged('post_install', '-at_install')
class TestSorConsignmentAgreementsInstall(TransactionCase):
    """Module install — key fields and methods are present on sor.agreement."""

    def test_agreement_types_available(self):
        selection = dict(self.env['sor.agreement']._fields['agreement_type'].selection)
        self.assertIn('consignment_in', selection)
        self.assertIn('consignment_out', selection)

    def test_fields_on_agreement(self):
        fields = self.env['sor.agreement']._fields
        self.assertIn('source_consignment_id', fields)
        self.assertIn('picking_count', fields)
        self.assertIn('move_ids', fields)
        self.assertIn('sor_compound_status', fields)

    def test_get_partner_location_method_exists(self):
        self.assertTrue(
            hasattr(self.env['sor.agreement'], '_get_partner_location'),
            '_get_partner_location method not found on sor.agreement',
        )


# ---------------------------------------------------------------------------
# Class 2 — Fixture-backed tests
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSorConsignmentAgreementsSetup(TransactionCase):
    """Picking creation, location resolution, guards, and compound status."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Test Consignor'})

        # Storable product — Odoo 19 uses type='consu' + is_storable=True.
        # product_type=False bypasses sor_artwork's artwork-specific constraints
        # (creator, dimensions) — this fixture is a generic storable product.
        cls.product = cls.env['product.template'].create({
            'name': 'Test Artwork',
            'type': 'consu',
            'is_storable': True,
            'product_type': False,
        })

        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )

        # Partners/External pool — provisioned by sor_tracking post_init_hook
        cls.partners_external_loc = cls.env['stock.location'].search([
            ('name', '=', 'Partners/External'),
            ('company_id', '=', cls.company.id),
            ('usage', '=', 'internal'),
        ], limit=1)

        cls.receipt_type = cls.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id', '=', cls.warehouse.id),
        ], limit=1)
        cls.delivery_type = cls.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id', '=', cls.warehouse.id),
        ], limit=1)

        # Consignment In agreement — draft, no lines initially
        cls.consignment_in = cls.env['sor.agreement'].create({
            'primary_partner_id': cls.partner.id,
            'agreement_type': 'consignment_in',
        })

        # Consignment Out agreement — draft, linked to the In
        cls.consignment_out = cls.env['sor.agreement'].create({
            'primary_partner_id': cls.partner.id,
            'agreement_type': 'consignment_out',
            'source_consignment_id': cls.consignment_in.id,
        })

    def setUp(self):
        super().setUp()
        # Prevent _generate_draft_pdf from attempting wkhtmltopdf renders in CI.
        patcher = patch.object(
            type(self.env['sor.agreement']),
            '_generate_draft_pdf',
            return_value=None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    # ------------------------------------------------------------------
    # _get_partner_location
    # ------------------------------------------------------------------

    def test_get_partner_location_returns_partners_external(self):
        if not self.partners_external_loc:
            self.skipTest('Partners/External pool not provisioned — sor_tracking not installed')
        location = self.consignment_in._get_partner_location(self.partner, 'in')
        self.assertEqual(location.name, 'Partners/External')

    # ------------------------------------------------------------------
    # action_create_intake — picking creation (BUG-04: renamed from action_receive_artwork)
    # ------------------------------------------------------------------

    def test_create_intake_creates_mvi_picking(self):
        result = self.consignment_in.action_create_intake()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.picking_type_id.code, 'incoming')

    def test_create_intake_source_is_partners_external(self):
        if not self.partners_external_loc:
            self.skipTest('Partners/External pool not provisioned — sor_tracking not installed')
        result = self.consignment_in.action_create_intake()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.location_id.name, 'Partners/External')

    def test_create_intake_dest_is_warehouse_stock(self):
        result = self.consignment_in.action_create_intake()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.location_dest_id, self.receipt_type.default_location_dest_id)

    def test_create_intake_linked_to_agreement(self):
        result = self.consignment_in.action_create_intake()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.agreement_id, self.consignment_in)

    def test_create_intake_returns_modal(self):
        result = self.consignment_in.action_create_intake()
        self.assertEqual(result.get('target'), 'new')

    def test_create_intake_creates_moves_per_line(self):
        # Create a fresh agreement with one line to verify move creation
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
            'line_ids': [(0, 0, {'product_id': self.product.id})],
        })
        result = agreement.action_create_intake()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(len(picking.move_ids), 1)
        self.assertEqual(picking.move_ids.product_id, self.product.product_variant_id)

    def test_create_intake_guard_raises_on_active(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
            'state': 'active',
        })
        with self.assertRaises(UserError):
            agreement.action_create_intake()

    def test_create_intake_guard_raises_on_closed(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
            'state': 'closed',
        })
        with self.assertRaises(UserError):
            agreement.action_create_intake()

    def test_create_intake_guard_raises_on_pending_signature(self):
        """BUG-10 Point 1: intake button guard now enforces Draft state only."""
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
            'state': 'pending_signature',
        })
        with self.assertRaises(UserError):
            agreement.action_create_intake()

    # ------------------------------------------------------------------
    # action_create_release — picking creation (BUG-04: renamed from action_release_artwork)
    # ------------------------------------------------------------------

    def test_create_release_creates_mvo_picking(self):
        result = self.consignment_out.action_create_release()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.picking_type_id.code, 'outgoing')

    def test_create_release_source_is_warehouse_stock(self):
        result = self.consignment_out.action_create_release()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.location_id, self.delivery_type.default_location_src_id)

    def test_create_release_dest_is_partners_external(self):
        if not self.partners_external_loc:
            self.skipTest('Partners/External pool not provisioned — sor_tracking not installed')
        result = self.consignment_out.action_create_release()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.location_dest_id.name, 'Partners/External')

    def test_create_release_linked_to_agreement(self):
        result = self.consignment_out.action_create_release()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.agreement_id, self.consignment_out)

    def test_create_release_returns_modal(self):
        result = self.consignment_out.action_create_release()
        self.assertEqual(result.get('target'), 'new')

    def test_create_release_guard_raises_on_active(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_out',
            'state': 'active',
        })
        with self.assertRaises(UserError):
            agreement.action_create_release()

    # ------------------------------------------------------------------
    # sor_compound_status
    # ------------------------------------------------------------------

    def test_compound_status_empty_when_no_out_pickings(self):
        # Active consignment_in with no confirmed out-agreement pickings must be falsy
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
            'state': 'active',
        })
        self.assertFalse(agreement.sor_compound_status)

    def test_compound_status_shows_when_picking_done(self):
        # Set up an active In agreement and a linked Out agreement with a product line
        in_agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
            'state': 'active',
        })
        out_agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_out',
            'source_consignment_id': in_agreement.id,
            'line_ids': [(0, 0, {'product_id': self.product.id})],
        })

        # Create a release picking via the action so locations are set correctly
        result = out_agreement.action_create_release()
        picking = self.env['stock.picking'].browse(result['res_id'])

        # Confirm the picking so moves are assigned quantities
        picking.action_confirm()
        # Set demanded quantity to 1 on every move so button_validate can proceed
        for move in picking.move_ids:
            move.quantity = 1.0
        # Validate the picking — _action_done will invalidate sor_compound_status
        picking.button_validate()

        self.assertEqual(picking.state, 'done')
        # Force recompute after invalidation
        in_agreement.invalidate_recordset(['sor_compound_status'])
        self.assertEqual(in_agreement.sor_compound_status, 'Active | Consigned out')

    # ------------------------------------------------------------------
    # picking_count
    # ------------------------------------------------------------------

    def test_picking_count_updates(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
        })
        self.assertEqual(agreement.picking_count, 0)
        result = agreement.action_create_intake()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.agreement_id, agreement)
        agreement.invalidate_recordset(['picking_count'])
        self.assertEqual(agreement.picking_count, 1)

    # ------------------------------------------------------------------
    # action_link_existing_intake
    # ------------------------------------------------------------------

    def test_link_existing_intake_returns_window_action(self):
        result = self.consignment_in.action_link_existing_intake()
        self.assertEqual(result.get('type'), 'ir.actions.act_window')
        self.assertEqual(result.get('target'), 'new')

    def test_link_existing_intake_guard_raises_on_active(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
            'state': 'active',
        })
        with self.assertRaises(UserError):
            agreement.action_link_existing_intake()

    # ------------------------------------------------------------------
    # action_link_existing_release
    # ------------------------------------------------------------------

    def test_link_existing_release_returns_window_action(self):
        result = self.consignment_out.action_link_existing_release()
        self.assertEqual(result.get('type'), 'ir.actions.act_window')
        self.assertEqual(result.get('target'), 'new')

    def test_link_existing_release_guard_raises_on_active(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_out',
            'state': 'active',
        })
        with self.assertRaises(UserError):
            agreement.action_link_existing_release()

    # ------------------------------------------------------------------
    # stock.picking.action_open_picking_modal
    # ------------------------------------------------------------------

    def test_action_open_picking_modal_returns_modal(self):
        result = self.consignment_in.action_create_intake()
        picking = self.env['stock.picking'].browse(result['res_id'])
        modal_result = picking.action_open_picking_modal()
        self.assertEqual(modal_result.get('target'), 'new')
        self.assertEqual(modal_result.get('res_id'), picking.id)
        self.assertEqual(modal_result.get('res_model'), 'stock.picking')

    # ------------------------------------------------------------------
    # BUG-10 — Lifecycle guardrails
    # ------------------------------------------------------------------

    def test_create_intake_guard_raises_on_pending_signature_state(self):
        """BUG-10 Point 1: guard now enforces Draft-only, not Draft+Pending."""
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
            'state': 'pending_signature',
        })
        with self.assertRaises(UserError):
            agreement.action_create_intake()

    def test_mark_sent_for_signature_raises_without_pickings(self):
        """BUG-10 Point 2: action_send_for_signature gates on linked movements for consignments."""
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
        })
        self.assertFalse(agreement.picking_ids)
        with self.assertRaises(UserError):
            agreement.action_send_for_signature()

    def test_cannot_unlink_picking_with_agreement(self):
        """BUG-10 Point 3: picking.unlink() raises UserError when agreement_id is set."""
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
        })
        result = agreement.action_create_intake()
        picking = self.env['stock.picking'].browse(result['res_id'])
        self.assertEqual(picking.agreement_id, agreement)
        with self.assertRaises(UserError):
            picking.unlink()

    def test_draft_agreement_deletion_sets_picking_agreement_null(self):
        """BUG-10 Point 4: ondelete='set null' on picking.agreement_id is confirmed.

        Deleting a Draft agreement nullifies picking.agreement_id via the ORM's
        ondelete='set null' cascade, leaving the picking intact and unlinked.
        """
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'agreement_type': 'consignment_in',
        })
        result = agreement.action_create_intake()
        picking_id = result['res_id']
        picking = self.env['stock.picking'].browse(picking_id)
        self.assertEqual(picking.agreement_id, agreement)
        # Delete the agreement — ondelete='set null' nullifies picking.agreement_id
        agreement.unlink()
        # Re-read the picking from DB to bypass ORM cache
        picking = self.env['stock.picking'].browse(picking_id)
        self.assertTrue(picking.exists(), 'Picking should survive agreement deletion')
        self.assertFalse(picking.agreement_id)
