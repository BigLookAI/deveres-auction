from odoo.tests import TransactionCase


class TestSorBuyerInvoiceContactRoles(TransactionCase):
    """Bridge: partner_share rule override lets art-world contacts be visible
    so that related field traversal (partner_id.ref) returns the correct value."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', cls.env.company.id)],
            limit=1,
        )

    def _make_invoice(self, partner):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': self.journal.id,
        })

    def test_partner_ref_visible_for_art_world_contact(self):
        """partner_ref on account.move returns ref when contact has partner_share=True
        and no company_id — the scenario that fails without this bridge."""
        partner = self.env['res.partner'].create({
            'name': 'Test Art World Bidder',
            'ref': 'AW-001',
            # is_company=False, no user → partner_share=True by default
        })
        move = self._make_invoice(partner)
        self.assertEqual(
            move.partner_ref, 'AW-001',
            'partner_ref must return the partner ref for art-world contacts',
        )

    def test_partner_ref_blank_when_no_ref_set(self):
        """When partner.ref is empty, partner_ref on account.move is blank — no error."""
        partner = self.env['res.partner'].create({
            'name': 'Test Art World Bidder No Ref',
            # ref deliberately not set
        })
        move = self._make_invoice(partner)
        self.assertFalse(
            move.partner_ref,
            'partner_ref must be empty when partner.ref is not set — no error raised',
        )

    def test_partner_ref_works_for_company_partner(self):
        """partner_ref also resolves correctly for company contacts (no regression)."""
        partner = self.env['res.partner'].create({
            'name': 'Test Gallery Ltd',
            'is_company': True,
            'ref': 'GAL-007',
        })
        move = self._make_invoice(partner)
        self.assertEqual(move.partner_ref, 'GAL-007')

    def test_bridge_auto_installs(self):
        """Both parent modules are installed — verify bridge is installed."""
        bridge = self.env['ir.module.module'].search(
            [('name', '=', 'sor_buyer_invoice_contact_roles')],
        )
        self.assertEqual(
            bridge.state, 'installed',
            'sor_buyer_invoice_contact_roles must auto-install when both parents are installed',
        )
