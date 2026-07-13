# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPartnerVisibility(TransactionCase):
    """Cross-company partner visibility tests for Story 04.

    Verifies that art-world contacts (partner_share=True, company_id=False)
    are visible to internal users regardless of which company is active.
    AC 1, AC 3 from Story 04 — Cross-Company Partner Visibility.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_a = cls.env['res.company'].search([], limit=1)
        # Create a second company for cross-company visibility tests.
        cls.company_b = cls.env['res.company'].create({
            'name': 'Test Company B — partner_visibility suite',
        })

        # Create an art-world contact with company_id=False (globally-accessible SOR contact).
        # The sor_contact_roles create override auto-assigns company_id when the key is
        # absent or falsy; bypass it with a direct SQL NULL after creation.
        partner = cls.env['res.partner'].sudo().create({
            'name': 'Test Artist — partner_visibility suite',
            'is_company': False,
        })
        cls.env.cr.execute(
            'UPDATE res_partner SET company_id = NULL WHERE id = %s',
            (partner.id,),
        )
        partner.invalidate_recordset(['company_id'])
        cls.art_contact = partner

        # Create an internal user whose only accessible company is company_b.
        cls.user_b = cls.env['res.users'].sudo().create({
            'name': 'User B — partner_visibility suite',
            'login': 'test_user_b_visibility_suite',
            'email': 'test_user_b_visibility@example.com',
            'company_id': cls.company_b.id,
            'company_ids': [Command.set([cls.company_b.id])],
        })

    def test_art_contact_visible_from_other_company(self):
        """A contact with company_id=False is visible when active company is different.

        This test verifies the relaxed base.res_partner_rule domain introduced in
        sor_contact_roles. The domain allows company_id=False contacts to pass the
        partner visibility rule, making them accessible to all internal users.
        """
        env_b = self.env(user=self.user_b)
        result = env_b['res.partner'].search([('id', '=', self.art_contact.id)])
        self.assertEqual(
            len(result),
            1,
            'Art-world contact (company_id=False) must be visible to a user '
            'in a different company. Check that base.res_partner_rule has been '
            'overridden in sor_contact_roles with the company_id=False clause.',
        )

    def test_company_assigned_contact_not_exposed_to_other_company(self):
        """A contact with company_id set to Company A is not visible from Company B.

        AC 2: The company_id=False relaxation must not leak contacts that have a specific
        company assignment. Only globally-accessible art-world contacts (company_id=False)
        benefit from the relaxed rule.
        """
        company_scoped = self.env['res.partner'].sudo().create({
            'name': 'Company A Contact — partner_visibility suite',
            'is_company': False,
            'company_id': self.company_a.id,
        })
        env_b = self.env(user=self.user_b)
        result = env_b['res.partner'].search([('id', '=', company_scoped.id)])
        self.assertEqual(
            len(result),
            0,
            'A contact assigned to Company A (company_id set) must NOT be visible to a '
            'user in Company B. The company_id=False relaxation applies only to '
            'globally-accessible art-world contacts.',
        )
