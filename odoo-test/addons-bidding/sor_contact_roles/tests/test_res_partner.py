# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResPartnerContactTypes(TransactionCase):
    """Test contact type assignment and validation on res.partner."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']

        # Find existing contact types — new hierarchy
        cls.creator_type = cls.ContactType.search([
            ('code', '=', 'creator'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.contact_type = cls.ContactType.search([
            ('code', '=', 'contact'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.artist_subtype = cls.ContactType.search([
            ('code', '=', 'artist'),
            ('parent_type_id', '!=', False),
        ], limit=1)
        cls.bidder_subtype = cls.ContactType.search([
            ('code', '=', 'bidder'),
            ('parent_type_id', '!=', False),
        ], limit=1)

        # Create test partner
        cls.partner = cls.Partner.create({
            'name': 'Test Contact',
        })

    def test_multiple_contact_types_assignment(self):
        """A contact can have multiple types simultaneously."""
        self.partner.write({
            'contact_types': [
                Command.link(self.creator_type.id),
                Command.link(self.contact_type.id),
            ],
        })
        self.assertIn(self.creator_type, self.partner.contact_types)
        self.assertIn(self.contact_type, self.partner.contact_types)
        self.assertTrue(self.partner.is_creator)
        self.assertTrue(self.partner.is_contact)

    def test_subtype_parent_auto_assignment(self):
        """Parent type is auto-assigned when sub-type is assigned."""
        self.partner.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertIn(self.creator_type, self.partner.contact_types)
        self.assertIn(self.artist_subtype, self.partner.contact_subtypes)
        self.assertTrue(self.partner.is_creator)
        self.assertTrue(self.partner.is_artist)

    def test_subtype_parent_auto_assignment_contact(self):
        """Contact parent type is auto-assigned when Contact sub-type is assigned."""
        if self.bidder_subtype:
            partner2 = self.Partner.create({'name': 'Auto-Assign Bidder'})
            partner2.write({
                'contact_subtypes': [Command.link(self.bidder_subtype.id)],
            })
            self.assertIn(self.contact_type, partner2.contact_types)
            self.assertIn(self.bidder_subtype, partner2.contact_subtypes)
            self.assertTrue(partner2.is_contact)
            self.assertTrue(partner2.is_bidder)

    def test_subtype_removal_when_parent_removed(self):
        """Sub-types are removed when parent is removed."""
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.partner.write({
            'contact_subtypes': [Command.clear()],
            'contact_types': [(6, 0, [])],
        })
        self.partner._onchange_contact_types()
        self.partner = self.partner.browse(self.partner.id)
        self.assertNotIn(self.creator_type, self.partner.contact_types)
        self.assertFalse(self.partner.contact_subtypes)

    def test_multiple_subtypes_same_parent(self):
        """Multiple sub-types from same parent can be assigned."""
        buyer_subtype = self.ContactType.search([('code', '=', 'buyer')], limit=1)
        if self.bidder_subtype and buyer_subtype:
            self.partner.write({
                'contact_types': [Command.link(self.contact_type.id)],
                'contact_subtypes': [
                    Command.link(self.bidder_subtype.id),
                    Command.link(buyer_subtype.id),
                ],
            })
            self.assertIn(self.bidder_subtype, self.partner.contact_subtypes)
            self.assertIn(buyer_subtype, self.partner.contact_subtypes)
            self.assertTrue(self.partner.is_contact)
            self.assertTrue(self.partner.is_bidder)

    def test_contact_without_types(self):
        """Contacts without types behave normally."""
        partner = self.Partner.create({'name': 'Normal Contact'})
        self.assertFalse(partner.contact_types)
        self.assertFalse(partner.contact_subtypes)
        self.assertFalse(partner.is_creator)
        self.assertFalse(partner.is_contact)
        self.assertEqual(partner.name, 'Normal Contact')

    def test_computed_fields_update(self):
        """Computed flags update when types change."""
        self.assertFalse(self.partner.is_creator)
        self.assertFalse(self.partner.is_artist)

        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.is_creator)

        self.partner.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertTrue(self.partner.is_creator)
        self.assertTrue(self.partner.is_artist)

    def test_has_creator_type_computed_field(self):
        """has_creator_type computed field controls UI visibility."""
        self.assertFalse(self.partner.has_creator_type)

        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.has_creator_type)

        partner2 = self.Partner.create({'name': 'Test Artist'})
        partner2.write({
            'contact_subtypes': [Command.link(self.artist_subtype.id)],
        })
        self.assertTrue(partner2.has_creator_type)

    def test_has_contact_type_computed_field(self):
        """has_contact_type computed field controls UI visibility."""
        self.assertFalse(self.partner.has_contact_type)

        self.partner.write({
            'contact_types': [Command.link(self.contact_type.id)],
        })
        self.assertTrue(self.partner.has_contact_type)

        if self.bidder_subtype:
            partner2 = self.Partner.create({'name': 'Test Bidder'})
            partner2.write({
                'contact_subtypes': [Command.link(self.bidder_subtype.id)],
            })
            self.assertTrue(partner2.has_contact_type)

    def test_show_subtypes_computed_field(self):
        """show_subtypes field controls sub-type field visibility."""
        self.assertFalse(self.partner.show_subtypes)

        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(self.partner.show_subtypes)

        # Remove Creator, assign Contact type — should show sub-types
        self.partner.write({
            'contact_types': [(6, 0, [self.contact_type.id])],
            'contact_subtypes': [Command.clear()],
        })
        self.assertTrue(self.partner.show_subtypes)

        # No parent types — sub-types hidden
        self.partner.write({
            'contact_types': [Command.clear()],
            'contact_subtypes': [Command.clear()],
        })
        self.assertFalse(self.partner.show_subtypes)


@tagged('post_install', '-at_install')
class TestResPartnerMultiCompany(TransactionCase):
    """Test multi-company support for contact types."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']
        cls.Company = cls.env['res.company']

        cls.company_a = cls.Company.search([('name', '=', 'Company A')], limit=1)
        if not cls.company_a:
            cls.company_a = cls.Company.create({'name': 'Company A'})

        cls.company_b = cls.Company.search([('name', '=', 'Company B')], limit=1)
        if not cls.company_b:
            cls.company_b = cls.Company.create({'name': 'Company B'})

        cls.creator_type = cls.ContactType.search([
            ('code', '=', 'creator'),
            ('company_id', '=', False),
        ], limit=1)

        cls.partner = cls.Partner.create({'name': 'Multi-Company Contact'})

    def test_global_contact_types_visible_all_companies(self):
        """Global contact types are visible in all companies."""
        self.env = self.env(context=dict(self.env.context, allowed_company_ids=[self.company_a.id]))
        creator_in_a = self.ContactType.search([
            ('code', '=', 'creator'),
            ('company_id', '=', False),
        ], limit=1)
        self.assertTrue(creator_in_a)

        self.env = self.env(context=dict(self.env.context, allowed_company_ids=[self.company_b.id]))
        creator_in_b = self.ContactType.search([
            ('code', '=', 'creator'),
            ('company_id', '=', False),
        ], limit=1)
        self.assertTrue(creator_in_b)

    def test_contact_types_persist_across_companies(self):
        """Contact type assignments persist across companies."""
        self.env = self.env(context=dict(self.env.context, allowed_company_ids=[self.company_a.id]))
        self.partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertIn(self.creator_type, self.partner.contact_types)
        self.assertTrue(self.partner.is_creator)

        self.env = self.env(context=dict(self.env.context, allowed_company_ids=[self.company_b.id]))
        self.assertIn(self.creator_type, self.partner.contact_types)
        self.assertTrue(self.partner.is_creator)

    def test_company_specific_contact_types(self):
        """Company-specific contact types work correctly."""
        self.ContactType.create({
            'name': 'Company A Type',
            'code': 'company_a_type',
            'type_category': 'other',
            'company_id': self.company_a.id,
        })

        self.env = self.env(context=dict(self.env.context, allowed_company_ids=[self.company_a.id]))
        found_type = self.ContactType.search([
            ('code', '=', 'company_a_type'),
            ('company_id', '=', self.company_a.id),
        ], limit=1)
        self.assertTrue(found_type)
