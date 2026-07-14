# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartnerNavigation(TransactionCase):
    """Tests for default_get override — contact type pre-assignment via context.

    Story 04: Navigation — AC3 and AC4.
    When a new partner is created from a type-specific window action, the action
    passes ``default_contact_type_code`` in the context. The ``default_get``
    override reads this key and pre-assigns the corresponding parent type so that
    gallery staff do not need to select a type manually.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']

        cls.creator_type = cls.ContactType.search(
            [('code', '=', 'creator'), ('parent_type_id', '=', False)],
            limit=1,
        )
        cls.contact_type = cls.ContactType.search(
            [('code', '=', 'contact'), ('parent_type_id', '=', False)],
            limit=1,
        )

    def test_default_get_creator_context(self):
        """default_get pre-assigns Creator type when context has code='creator'."""
        self.assertTrue(
            self.creator_type,
            "Creator parent type must exist in the database (seeded by data file)",
        )
        Partner = self.env['res.partner'].with_context(default_contact_type_code='creator')
        defaults = Partner.default_get(['name', 'contact_types'])
        self.assertIn('contact_types', defaults, "contact_types should be in defaults")
        assigned_ids = [cmd[1] for cmd in defaults['contact_types'] if cmd[0] == 4]
        self.assertIn(
            self.creator_type.id,
            assigned_ids,
            "Creator type should be pre-assigned in Creator context",
        )

    def test_default_get_contact_context(self):
        """default_get pre-assigns Contact type when context has code='contact'."""
        self.assertTrue(
            self.contact_type,
            "Contact parent type must exist in the database (seeded by data file)",
        )
        Partner = self.env['res.partner'].with_context(default_contact_type_code='contact')
        defaults = Partner.default_get(['name', 'contact_types'])
        self.assertIn('contact_types', defaults, "contact_types should be in defaults")
        assigned_ids = [cmd[1] for cmd in defaults['contact_types'] if cmd[0] == 4]
        self.assertIn(
            self.contact_type.id,
            assigned_ids,
            "Contact type should be pre-assigned in Contact context",
        )

    def test_default_get_no_context(self):
        """default_get does not pre-assign any type when no context key is set."""
        Partner = self.env['res.partner']
        defaults = Partner.default_get(['name', 'contact_types'])
        # contact_types may be absent or empty when no context key is set
        assigned_types = defaults.get('contact_types', [])
        contact_type_codes_assigned = []
        for cmd in assigned_types:
            if cmd[0] == 4:
                t = self.ContactType.browse(cmd[1])
                contact_type_codes_assigned.append(t.code)
        self.assertNotIn(
            'creator',
            contact_type_codes_assigned,
            "Creator type must not be pre-assigned without context",
        )
        self.assertNotIn(
            'contact',
            contact_type_codes_assigned,
            "Contact type must not be pre-assigned without context",
        )

    def test_default_get_unknown_code_is_noop(self):
        """default_get is a no-op when context code matches no contact type record."""
        Partner = self.env['res.partner'].with_context(
            default_contact_type_code='nonexistent_type_xyz',
        )
        defaults = Partner.default_get(['name', 'contact_types'])
        # Should not raise; contact_types should be absent or empty
        assigned_types = defaults.get('contact_types', [])
        self.assertEqual(
            assigned_types,
            [],
            "No types should be assigned for an unknown type code",
        )

    def test_default_get_creator_creates_partner_with_type(self):
        """Creating a partner in Creator context results in Creator type assigned."""
        partner = self.env['res.partner'].with_context(
            default_contact_type_code='creator',
        ).create({'name': 'Auto-Creator Navigation Test'})
        self.assertIn(
            self.creator_type,
            partner.contact_types,
            "Created partner should have Creator type",
        )
        self.assertTrue(partner.is_creator)

    def test_default_get_contact_creates_partner_with_type(self):
        """Creating a partner in Contact context results in Contact type assigned."""
        partner = self.env['res.partner'].with_context(
            default_contact_type_code='contact',
        ).create({'name': 'Auto-Contact Navigation Test'})
        self.assertIn(
            self.contact_type,
            partner.contact_types,
            "Created partner should have Contact type",
        )
        self.assertTrue(partner.is_contact)

    # ==========================================
    # AC1, AC2, AC6 — window action domain filtering
    # ==========================================

    def test_creators_domain_returns_only_creators(self):
        """Creators window action domain returns partners with Creator type only."""
        creator_partner = self.env['res.partner'].create({
            'name': 'Nav Test Creator',
            'contact_types': [(4, self.creator_type.id)],
        })
        contact_partner = self.env['res.partner'].create({
            'name': 'Nav Test Contact Only',
            'contact_types': [(4, self.contact_type.id)],
        })
        untyped_partner = self.env['res.partner'].create({
            'name': 'Nav Test Untyped',
        })

        creators = self.env['res.partner'].search(
            [('contact_types.code', '=', 'creator')],
        )
        self.assertIn(creator_partner, creators, "Creator partner must appear in Creators domain")
        self.assertNotIn(contact_partner, creators, "Contact-only partner must not appear in Creators domain")
        self.assertNotIn(untyped_partner, creators, "Untyped partner must not appear in Creators domain")

    def test_contacts_domain_returns_only_contact_type(self):
        """Contacts window action domain returns partners with Contact type only."""
        contact_partner = self.env['res.partner'].create({
            'name': 'Nav Test Contact',
            'contact_types': [(4, self.contact_type.id)],
        })
        creator_partner = self.env['res.partner'].create({
            'name': 'Nav Test Creator Only',
            'contact_types': [(4, self.creator_type.id)],
        })
        untyped_partner = self.env['res.partner'].create({
            'name': 'Nav Test Untyped 2',
        })

        contacts = self.env['res.partner'].search(
            [('contact_types.code', '=', 'contact')],
        )
        self.assertIn(contact_partner, contacts, "Contact partner must appear in Contacts domain")
        self.assertNotIn(creator_partner, contacts, "Creator-only partner must not appear in Contacts domain")
        self.assertNotIn(untyped_partner, contacts, "Untyped partner must not appear in Contacts domain")

    # ==========================================
    # AC5 — contacts.menu_contacts hidden
    # ==========================================

    def test_default_contacts_menu_hidden(self):
        """contacts.menu_contacts is inactive — the default Odoo Contacts menu is suppressed."""
        menu = self.env.ref('contacts.menu_contacts', raise_if_not_found=False)
        if not menu:
            self.skipTest("contacts.menu_contacts not found — may not be installed")
        self.assertFalse(
            menu.active,
            "contacts.menu_contacts must be inactive (hidden by sor_contact_roles)",
        )
