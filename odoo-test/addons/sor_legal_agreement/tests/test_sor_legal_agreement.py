from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorLegalAgreementInstall(TransactionCase):
    """Module install — key models and fields are present."""

    def test_models_exist(self):
        self.assertIn('sor.agreement', self.env)
        self.assertIn('sor.agreement.line', self.env)

    def test_picking_has_agreement_field(self):
        self.assertIn('agreement_id', self.env['stock.picking']._fields)

    def test_company_has_logo_pdf_field(self):
        self.assertIn('logo_pdf', self.env['res.company']._fields)


@tagged('post_install', '-at_install')
class TestSorAgreementCreate(TransactionCase):
    """Agreement creation — sequence assignment and required fields."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Test Counterparty'})
        # sor_artwork adds required fields (product_type, dimensions, creator_id)
        # to product.template that would require complex setup to satisfy.  This
        # test only needs *any* valid product to verify that agreement lines can
        # reference products — creating a new one from scratch is not necessary.
        cls.product = cls.env['product.template'].search([], limit=1)
        if not cls.product:
            cls.skipTest(cls, 'No product.template records found — cannot test agreement lines')

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

    def test_name_auto_assigned_from_sequence(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
        })
        self.assertNotEqual(agreement.name, 'New Agreement')
        self.assertRegex(agreement.name, r'^AGR/\d{4}/\d+$')

    def test_default_state_is_draft(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
        })
        self.assertEqual(agreement.state, 'draft')

    def test_company_id_defaults_to_current_company(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
        })
        self.assertEqual(agreement.company_id, self.env.company)

    def test_line_added_to_agreement(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'line_ids': [(0, 0, {'product_id': self.product.id})],
        })
        self.assertEqual(len(agreement.line_ids), 1)
        self.assertEqual(agreement.line_ids.product_id, self.product)


@tagged('post_install', '-at_install')
class TestSorAgreementStateMachine(TransactionCase):
    """State machine transitions and guard conditions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Test Counterparty'})

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

    def _make_agreement(self, state='draft'):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
        })
        if state != 'draft':
            agreement.write({'state': state})
        return agreement

    def test_draft_to_pending_signature(self):
        agreement = self._make_agreement('draft')
        # Patch PDF rendering so the test does not require wkhtmltopdf
        with patch.object(
            type(self.env['ir.actions.report']),
            '_render_qweb_pdf',
            return_value=(b'%PDF-1.4 fake', 'pdf'),
        ):
            agreement.action_send_for_signature()
        self.assertEqual(agreement.state, 'pending_signature')

    def test_draft_to_pending_signature_attaches_pdf(self):
        agreement = self._make_agreement('draft')
        with patch.object(
            type(self.env['ir.actions.report']),
            '_render_qweb_pdf',
            return_value=(b'%PDF-1.4 fake', 'pdf'),
        ):
            agreement.action_send_for_signature()
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'sor.agreement'),
            ('res_id', '=', agreement.id),
            ('mimetype', '=', 'application/pdf'),
        ])
        self.assertEqual(len(attachments), 1)

    def test_send_for_signature_requires_draft(self):
        agreement = self._make_agreement('pending_signature')
        with self.assertRaises(UserError):
            agreement.action_send_for_signature()

    def test_pending_signature_to_active(self):
        agreement = self._make_agreement('pending_signature')
        agreement.action_confirm_signed()
        self.assertEqual(agreement.state, 'active')

    def test_confirm_signed_requires_pending_signature(self):
        agreement = self._make_agreement('draft')
        with self.assertRaises(UserError):
            agreement.action_confirm_signed()

    def test_active_to_closed(self):
        agreement = self._make_agreement('active')
        agreement.action_close()
        self.assertEqual(agreement.state, 'closed')

    def test_close_requires_active(self):
        agreement = self._make_agreement('pending_signature')
        with self.assertRaises(UserError):
            agreement.action_close()

    def test_closed_is_terminal(self):
        agreement = self._make_agreement('closed')
        with self.assertRaises(UserError):
            agreement.action_close()


@tagged('post_install', '-at_install')
class TestSorAgreementDeletion(TransactionCase):
    """Deletion protection — only Draft agreements may be deleted."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Test Counterparty'})

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            type(self.env['sor.agreement']),
            '_generate_draft_pdf',
            return_value=None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_agreement(self, state='draft'):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
        })
        if state != 'draft':
            agreement.write({'state': state})
        return agreement

    def test_draft_can_be_deleted(self):
        agreement = self._make_agreement('draft')
        agreement_id = agreement.id
        agreement.unlink()
        self.assertFalse(self.env['sor.agreement'].browse(agreement_id).exists())

    def test_pending_signature_cannot_be_deleted(self):
        agreement = self._make_agreement('pending_signature')
        with self.assertRaises(UserError):
            agreement.unlink()

    def test_active_cannot_be_deleted(self):
        agreement = self._make_agreement('active')
        with self.assertRaises(UserError):
            agreement.unlink()

    def test_closed_cannot_be_deleted(self):
        agreement = self._make_agreement('closed')
        with self.assertRaises(UserError):
            agreement.unlink()


@tagged('post_install', '-at_install')
class TestSorAgreementMovementGate(TransactionCase):
    """_check_can_trigger_movement — bridge contract enforcement."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Test Counterparty'})

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            type(self.env['sor.agreement']),
            '_generate_draft_pdf',
            return_value=None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_active_agreement_passes_gate(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'state': 'active',
        })
        # Should not raise
        agreement._check_can_trigger_movement()

    def test_draft_agreement_blocks_movement(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
        })
        with self.assertRaises(UserError):
            agreement._check_can_trigger_movement()

    def test_pending_signature_blocks_movement(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'state': 'pending_signature',
        })
        with self.assertRaises(UserError):
            agreement._check_can_trigger_movement()

    def test_closed_agreement_blocks_movement(self):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'state': 'closed',
        })
        with self.assertRaises(UserError):
            agreement._check_can_trigger_movement()


@tagged('post_install', '-at_install')
class TestSorAgreementMultiCompany(TransactionCase):
    """Multi-company isolation — sequences and record rules."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            type(self.env['sor.agreement']),
            '_generate_draft_pdf',
            return_value=None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_per_company_sequence_exists(self):
        sequence = self.env['ir.sequence'].search([
            ('code', '=', 'sor.agreement'),
            ('company_id', '=', self.env.company.id),
        ])
        self.assertTrue(sequence, 'No sor.agreement sequence found for current company')

    def test_new_company_gets_sequence(self):
        company = self.env['res.company'].create({'name': 'Test Legal Co'})
        sequence = self.env['ir.sequence'].search([
            ('code', '=', 'sor.agreement'),
            ('company_id', '=', company.id),
        ])
        self.assertTrue(sequence, 'No sor.agreement sequence created for new company')

    def test_agreement_name_uses_company_sequence(self):
        company_b = self.env['res.company'].create({'name': 'Test Legal Co B'})
        agreement = self.env['sor.agreement'].with_company(company_b).create({
            'company_id': company_b.id,
        })
        self.assertRegex(agreement.name, r'^AGR/\d{4}/\d+$')
        self.assertEqual(agreement.company_id, company_b)


# ---------------------------------------------------------------------------
# Story 03 — Rescind and Regenerate
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSorAgreementRescind(TransactionCase):
    """action_rescind — revocation, replacement creation, and supersedes chain."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Test Counterparty Rescind'})
        cls.product = cls.env['product.template'].search([], limit=1)

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            type(self.env['sor.agreement']),
            '_generate_draft_pdf',
            return_value=None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_agreement(self, state='draft'):
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
        })
        if state != 'draft':
            agreement.write({'state': state})
        return agreement

    def test_rescind_pending_signature_revokes_original(self):
        agreement = self._make_agreement('pending_signature')
        agreement.action_rescind()
        self.assertEqual(agreement.state, 'revoked')

    def test_rescind_active_revokes_original(self):
        agreement = self._make_agreement('active')
        agreement.action_rescind()
        self.assertEqual(agreement.state, 'revoked')

    def test_rescind_draft_raises_user_error(self):
        agreement = self._make_agreement('draft')
        with self.assertRaises(UserError):
            agreement.action_rescind()

    def test_replacement_has_supersedes_id_pointing_to_original(self):
        original = self._make_agreement('pending_signature')
        original.action_rescind()
        replacement = self.env['sor.agreement'].search(
            [('supersedes_id', '=', original.id)], limit=1,
        )
        self.assertTrue(replacement, 'No replacement agreement found after rescind')
        self.assertEqual(replacement.supersedes_id, original)

    def test_original_superseded_by_id_points_to_replacement(self):
        original = self._make_agreement('active')
        original.action_rescind()
        replacement = self.env['sor.agreement'].search(
            [('supersedes_id', '=', original.id)], limit=1,
        )
        self.assertTrue(replacement)
        # Force recompute of the computed inverse field
        original.invalidate_recordset(['superseded_by_id'])
        self.assertEqual(original.superseded_by_id, replacement)

    def test_date_sent_for_signature_set_by_send_for_signature(self):
        agreement = self._make_agreement('draft')
        with patch.object(
            type(self.env['ir.actions.report']),
            '_render_qweb_pdf',
            return_value=(b'%PDF-1.4 fake', 'pdf'),
        ):
            agreement.action_send_for_signature()
        self.assertIsNotNone(agreement.date_sent_for_signature)
        self.assertEqual(agreement.date_sent_for_signature, fields.Date.today())

    def test_lines_copied_to_replacement(self):
        if not self.product:
            self.skipTest('No product.template records available')
        original = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'line_ids': [(0, 0, {'product_id': self.product.id})],
        })
        original.write({'state': 'pending_signature'})
        self.assertEqual(len(original.line_ids), 1)
        original.action_rescind()
        replacement = self.env['sor.agreement'].search(
            [('supersedes_id', '=', original.id)], limit=1,
        )
        self.assertTrue(replacement)
        self.assertEqual(len(replacement.line_ids), 1)
        self.assertEqual(replacement.line_ids.product_id, self.product)

    def test_revoked_agreement_cannot_be_deleted(self):
        agreement = self._make_agreement('active')
        agreement.action_rescind()
        self.assertEqual(agreement.state, 'revoked')
        with self.assertRaises(UserError):
            agreement.unlink()


# ---------------------------------------------------------------------------
# Story 04 — Staleness Alerting
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSorAgreementStaleness(TransactionCase):
    """is_stale computed field, _search_is_stale, and stale notification cron."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Test Counterparty Stale'})

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            type(self.env['sor.agreement']),
            '_generate_draft_pdf',
            return_value=None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_pending(self, date_sent=None, date_end=None):
        """Helper: create a pending_signature agreement with optional date fields."""
        vals = {
            'primary_partner_id': self.partner.id,
            'state': 'pending_signature',
        }
        if date_sent is not None:
            vals['date_sent_for_signature'] = date_sent
        if date_end is not None:
            vals['date_end'] = date_end
        return self.env['sor.agreement'].create(vals)

    def test_stale_by_sent_date_15_days_ago(self):
        today = fields.Date.today()
        agreement = self._make_pending(date_sent=today - timedelta(days=15))
        self.assertTrue(agreement.is_stale)

    def test_stale_by_end_date_3_days_from_now(self):
        today = fields.Date.today()
        agreement = self._make_pending(date_end=today + timedelta(days=3))
        self.assertTrue(agreement.is_stale)

    def test_not_stale_recent_sent_no_end_date(self):
        today = fields.Date.today()
        agreement = self._make_pending(date_sent=today - timedelta(days=5))
        self.assertFalse(agreement.is_stale)

    def test_draft_is_never_stale(self):
        today = fields.Date.today()
        agreement = self.env['sor.agreement'].create({
            'primary_partner_id': self.partner.id,
            'date_sent_for_signature': today - timedelta(days=30),
            'date_end': today - timedelta(days=10),
        })
        # State is draft (default) — staleness only applies to pending_signature
        self.assertFalse(agreement.is_stale)

    def test_search_is_stale_returns_stale_agreements(self):
        today = fields.Date.today()
        stale = self._make_pending(date_sent=today - timedelta(days=20))
        fresh = self._make_pending(date_sent=today - timedelta(days=5))
        results = self.env['sor.agreement'].search([('is_stale', '=', True)])
        self.assertIn(stale, results)
        self.assertNotIn(fresh, results)

    def test_notify_stale_sets_last_stale_notified(self):
        today = fields.Date.today()
        agreement = self._make_pending(date_sent=today - timedelta(days=20))
        self.assertFalse(agreement.last_stale_notified)
        self.env['sor.agreement']._action_notify_stale_agreements()
        self.assertEqual(agreement.last_stale_notified, today)

    def test_notify_stale_skips_already_notified(self):
        today = fields.Date.today()
        yesterday = today - timedelta(days=1)
        agreement = self._make_pending(date_sent=today - timedelta(days=20))
        # Pre-set the notification date to simulate already notified
        agreement.write({'last_stale_notified': yesterday})
        self.env['sor.agreement']._action_notify_stale_agreements()
        # last_stale_notified should remain as yesterday, not updated to today
        self.assertEqual(agreement.last_stale_notified, yesterday)


# ---------------------------------------------------------------------------
# Story 05 — Draft PDF on Save
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestSorAgreementDraftPdf(TransactionCase):
    """Draft PDF attachment lifecycle — create, replace on write, finalise on send."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Test Counterparty PDF'})

    # NOTE: No setUp mock for _generate_draft_pdf in this class — these tests
    # exercise the real PDF behaviour with _render_qweb_pdf mocked instead.

    def _pdf_patch(self):
        """Context manager: mock the low-level report renderer."""
        return patch.object(
            type(self.env['ir.actions.report']),
            '_render_qweb_pdf',
            return_value=(b'%PDF-1.4 fake', 'pdf'),
        )

    def _draft_attachments(self, agreement):
        return self.env['ir.attachment'].search([
            ('res_model', '=', 'sor.agreement'),
            ('res_id', '=', agreement.id),
            ('name', 'like', '(Draft).pdf'),
        ])

    def test_create_draft_generates_draft_pdf_attachment(self):
        with self._pdf_patch():
            agreement = self.env['sor.agreement'].create({
                'primary_partner_id': self.partner.id,
            })
        attachments = self._draft_attachments(agreement)
        self.assertEqual(len(attachments), 1)
        self.assertIn('(Draft).pdf', attachments.name)

    def test_write_draft_replaces_draft_pdf_no_duplicates(self):
        with self._pdf_patch():
            agreement = self.env['sor.agreement'].create({
                'primary_partner_id': self.partner.id,
            })
            # A second write should replace, not accumulate, the draft attachment
            agreement.write({'notes': 'Updated notes'})
        attachments = self._draft_attachments(agreement)
        self.assertEqual(len(attachments), 1, 'Expected exactly one draft PDF after write')

    def test_send_for_signature_removes_draft_attachment(self):
        with self._pdf_patch():
            agreement = self.env['sor.agreement'].create({
                'primary_partner_id': self.partner.id,
            })
            agreement.action_send_for_signature()
        draft_attachments = self._draft_attachments(agreement)
        self.assertEqual(len(draft_attachments), 0, 'Draft PDF should be removed after send')

    def test_send_for_signature_creates_final_pdf(self):
        with self._pdf_patch():
            agreement = self.env['sor.agreement'].create({
                'primary_partner_id': self.partner.id,
            })
            name_before_send = agreement.name
            agreement.action_send_for_signature()
        final_attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'sor.agreement'),
            ('res_id', '=', agreement.id),
            ('mimetype', '=', 'application/pdf'),
        ])
        self.assertEqual(len(final_attachments), 1)
        self.assertNotIn('(Draft)', final_attachments.name)
        self.assertEqual(final_attachments.name, f'{name_before_send}.pdf')

    def test_write_non_draft_does_not_generate_draft_pdf(self):
        with self._pdf_patch():
            agreement = self.env['sor.agreement'].create({
                'primary_partner_id': self.partner.id,
            })
            # Manually move to active without going through the signature workflow
            agreement.write({'state': 'active'})
            # Remove any draft attachments left from create/previous write
            self._draft_attachments(agreement).unlink()
            # Now write to the active agreement — no draft PDF should be produced
            agreement.write({'notes': 'Post-activation note'})
        draft_attachments = self._draft_attachments(agreement)
        self.assertEqual(len(draft_attachments), 0,
                         'write() on a non-draft agreement must not generate a draft PDF')
