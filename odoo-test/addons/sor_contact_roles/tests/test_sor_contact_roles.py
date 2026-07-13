# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ast

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.sor_contact_roles import post_init_hook


@tagged('post_install', '-at_install')
class TestSorContactRoles(TransactionCase):
    """Tests for sor_contact_roles: contact type creation, hierarchy,
    constraints, computed flags, and company scoping."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']

        # Locate the Creator parent type (seeded by data file)
        cls.creator_type = cls.ContactType.search(
            [('code', '=', 'creator'), ('parent_type_id', '=', False)],
            limit=1,
        )

    def test_contact_type_creation(self):
        """A contact type can be created with name, code, and parent."""
        ct = self.ContactType.create({
            'name': 'Test Sub-Creator — sor_contact_roles suite',
            'code': 'test_sub_creator_suite',
            'parent_type_id': self.creator_type.id,
            'type_category': 'creator',
        })
        self.assertEqual(ct.name, 'Test Sub-Creator — sor_contact_roles suite')
        self.assertEqual(ct.code, 'test_sub_creator_suite')
        self.assertEqual(ct.parent_type_id, self.creator_type)

    def test_parent_child_hierarchy(self):
        """A sub-type returns its parent via parent_type_id and appears
        in the parent's child_ids."""
        child = self.ContactType.create({
            'name': 'Test Hierarchy Child — sor_contact_roles suite',
            'code': 'test_hierarchy_child_suite',
            'parent_type_id': self.creator_type.id,
            'type_category': 'creator',
        })
        self.assertEqual(child.parent_type_id.id, self.creator_type.id)
        self.assertIn(child.id, self.creator_type.child_ids.ids)

    def test_circular_reference_constraint(self):
        """Assigning a type as its own ancestor raises ValidationError."""
        parent = self.ContactType.create({
            'name': 'Test Circular Parent — sor_contact_roles suite',
            'code': 'test_circular_parent_suite',
        })
        child = self.ContactType.create({
            'name': 'Test Circular Child — sor_contact_roles suite',
            'code': 'test_circular_child_suite',
            'parent_type_id': parent.id,
        })
        with self.assertRaises(ValidationError):
            parent.write({'parent_type_id': child.id})

    def test_duplicate_code_constraint(self):
        """Creating two contact types with the same code raises a
        constraint error."""
        self.ContactType.create({
            'name': 'Test Dupe Code A — sor_contact_roles suite',
            'code': 'test_dupe_code_suite',
        })
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.ContactType.create({
                'name': 'Test Dupe Code B — sor_contact_roles suite',
                'code': 'test_dupe_code_suite',
            })

    def test_computed_flag_is_creator(self):
        """A partner assigned the Creator contact type has is_creator=True;
        a partner with no contact types has is_creator=False."""
        partner = self.Partner.create({
            'name': 'Test Creator Partner — sor_contact_roles suite',
        })
        self.assertFalse(partner.is_creator)
        partner.write({
            'contact_types': [Command.link(self.creator_type.id)],
        })
        self.assertTrue(partner.is_creator)

    def test_creator_subtypes_filters_to_creator_only(self):
        """creator_subtypes returns only sub-types whose parent is Creator,
        not sub-types from other parent types on the same partner."""
        creator_type = self.ContactType.search(
            [('code', '=', 'creator'), ('parent_type_id', '=', False)], limit=1,
        )
        contact_type = self.ContactType.search(
            [('code', '=', 'contact'), ('parent_type_id', '=', False)], limit=1,
        )
        artist_type = self.ContactType.search(
            [('code', '=', 'artist'), ('parent_type_id', '=', creator_type.id)], limit=1,
        )
        bidder_type = self.ContactType.search(
            [('code', '=', 'bidder'), ('parent_type_id', '=', contact_type.id)], limit=1,
        )
        partner = self.Partner.create({
            'name': 'Test Creator+Contact — subtypes suite',
            'contact_types': [(4, creator_type.id), (4, contact_type.id)],
            'contact_subtypes': [(4, artist_type.id), (4, bidder_type.id)],
        })
        creator_sub_codes = set(partner.creator_subtypes.mapped('code'))
        self.assertIn('artist', creator_sub_codes, "creator_subtypes must include Artist")
        self.assertNotIn('bidder', creator_sub_codes, "creator_subtypes must not include Bidder")

    def test_contact_role_subtypes_filters_to_contact_only(self):
        """contact_role_subtypes returns only sub-types whose parent is Contact,
        not sub-types from other parent types on the same partner."""
        creator_type = self.ContactType.search(
            [('code', '=', 'creator'), ('parent_type_id', '=', False)], limit=1,
        )
        contact_type = self.ContactType.search(
            [('code', '=', 'contact'), ('parent_type_id', '=', False)], limit=1,
        )
        artist_type = self.ContactType.search(
            [('code', '=', 'artist'), ('parent_type_id', '=', creator_type.id)], limit=1,
        )
        bidder_type = self.ContactType.search(
            [('code', '=', 'bidder'), ('parent_type_id', '=', contact_type.id)], limit=1,
        )
        partner = self.Partner.create({
            'name': 'Test Contact+Creator — role subtypes suite',
            'contact_types': [(4, creator_type.id), (4, contact_type.id)],
            'contact_subtypes': [(4, artist_type.id), (4, bidder_type.id)],
        })
        contact_sub_codes = set(partner.contact_role_subtypes.mapped('code'))
        self.assertIn('bidder', contact_sub_codes, "contact_role_subtypes must include Bidder")
        self.assertNotIn('artist', contact_sub_codes, "contact_role_subtypes must not include Artist")

    def test_company_scoping_contact_types_shared(self):
        """Contact types are accessible across companies (shared master
        data); a record created in company A is readable from company B."""
        company_b = self.env['res.company'].create({
            'name': 'Test Company B — sor_contact_roles suite',
        })
        env_b = self.env(context=dict(
            self.env.context,
            allowed_company_ids=[company_b.id],
        ))
        ct_from_b = env_b['sor.contact.type'].search(
            [('code', '=', 'creator')],
            limit=1,
        )
        self.assertTrue(
            ct_from_b,
            "Creator contact type should be visible from Company B",
        )
        self.assertEqual(ct_from_b.id, self.creator_type.id)

    def test_post_init_hook_importable(self):
        """post_init_hook is importable as a top-level package attribute."""
        self.assertTrue(callable(post_init_hook))

    def test_post_init_hook_seeds_creator_hierarchy(self):
        """Creator parent type and Artist sub-type exist after install."""
        CT = self.env['sor.contact.type']
        creator = CT.search([('code', '=', 'creator'), ('parent_type_id', '=', False)], limit=1)
        self.assertTrue(creator, "Creator parent type must exist")
        artist = CT.search([('code', '=', 'artist'), ('parent_type_id', '=', creator.id)], limit=1)
        self.assertTrue(artist, "Artist sub-type must exist under Creator")

    def test_post_init_hook_seeds_contact_hierarchy(self):
        """Contact parent type exists with all five activity-earned sub-types."""
        CT = self.env['sor.contact.type']
        contact = CT.search([('code', '=', 'contact'), ('parent_type_id', '=', False)], limit=1)
        self.assertTrue(contact, "Contact parent type must exist")
        expected_codes = {'bidder', 'buyer', 'consignor', 'donor', 'lender'}
        actual_codes = set(CT.search([('parent_type_id', '=', contact.id)]).mapped('code'))
        self.assertTrue(
            expected_codes.issubset(actual_codes),
            "Contact sub-types missing: %s" % (expected_codes - actual_codes),
        )


@tagged('post_install', '-at_install')
class TestSorContactRolesSprint22(TransactionCase):
    """Story 01 + Story 02 — developer menu and toggle suppression additions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.Partner = cls.env['res.partner']
        cls.contact_type = cls.ContactType.search(
            [('code', '=', 'contact'), ('parent_type_id', '=', False)],
            limit=1,
        )

    def test_developer_action_has_active_test_false(self):
        """Story 01 AC 3: Contact Types developer action must have active_test=False
        in context so archived types are visible in the list."""
        action = self.env.ref(
            'sor_contact_roles.action_sor_contact_types_dev',
            raise_if_not_found=False,
        )
        self.assertTrue(action, 'Developer action action_sor_contact_types_dev not found')
        ctx = ast.literal_eval(action.context) if isinstance(action.context, str) else action.context
        self.assertIn('active_test', ctx, "Developer action context must include active_test")
        self.assertFalse(ctx.get('active_test'), "active_test must be False to show archived types")

    def test_is_company_blocked_when_is_contact_true(self):
        """Story 02 AC 3: setting is_company=True on a partner with is_contact=True raises ValidationError."""
        partner = self.Partner.create({'name': 'Test Contact Constraint — sprint22 suite'})
        partner.contact_types = [(4, self.contact_type.id)]
        self.assertTrue(partner.is_contact, "Partner must have is_contact=True after Contact type assigned")
        with self.assertRaises(ValidationError):
            partner.write({'is_company': True})

    def test_individual_contact_is_not_blocked(self):
        """Story 02 AC 2: assigning the Contact type to an individual partner does not raise an error."""
        partner = self.Partner.create({'name': 'Test Individual to Contact — sprint22 suite'})
        self.assertFalse(partner.is_contact)
        partner.contact_types = [(4, self.contact_type.id)]
        self.assertTrue(partner.is_contact)
