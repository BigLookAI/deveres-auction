# Part of Odoo. See LICENSE file for full copyright and licensing details.

import uuid

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestSorContactType(TransactionCase):
    """Test sor.contact.type model constraints and validations."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ContactType = cls.env['sor.contact.type']
        cls.test_uuid = uuid.uuid4().hex[:8]  # Unique identifier for this test run

        # Get existing types for testing
        cls.creator_type = cls.ContactType.search([
            ('code', '=', 'creator'),
            ('parent_type_id', '=', False),
        ], limit=1)
        cls.contact_type = cls.ContactType.search([
            ('code', '=', 'contact'),
            ('parent_type_id', '=', False),
        ], limit=1)

    @mute_logger('odoo.sql_db')
    def test_code_uniqueness(self):
        """Contact type codes must be unique."""
        unique_code = f'test_unique_{uuid.uuid4().hex[:8]}'

        contact_type = self.ContactType.create({
            'name': 'Test Unique',
            'code': unique_code,
            'type_category': 'other',
        })

        self.assertTrue(contact_type.exists())
        initial_count = self.ContactType.search_count([('code', '=', unique_code)])
        self.assertEqual(initial_count, 1)

        savepoint = self.env.cr.savepoint()
        duplicate = None
        try:
            duplicate = self.ContactType.create({
                'name': 'Test Unique 2',
                'code': unique_code,
                'type_category': 'other',
            })
            self.env.flush_all()
            savepoint.rollback()
            if duplicate and duplicate.exists():
                duplicate.unlink()
            self.fail("Uniqueness constraint should have prevented duplicate code creation")
        except Exception:  # noqa: BLE001
            savepoint.rollback()

        final_count = self.ContactType.search_count([('code', '=', unique_code)])
        self.assertEqual(final_count, 1, "Duplicate record should not have been created")

        contact_type.unlink()

    def test_circular_reference_prevention(self):
        """Circular references in hierarchy are prevented."""
        type_a = self.ContactType.create({
            'name': 'Type A',
            'code': f'type_a_{self.test_uuid}',
            'type_category': 'other',
        })
        type_b = self.ContactType.create({
            'name': 'Type B',
            'code': f'type_b_{self.test_uuid}',
            'type_category': 'other',
            'parent_type_id': type_a.id,
        })

        with self.assertRaises(ValidationError):
            type_a.write({'parent_type_id': type_b.id})

        type_b.unlink()
        type_a.unlink()

    def test_self_reference_prevention(self):
        """A type cannot be its own parent."""
        type_a = self.ContactType.create({
            'name': 'Type A',
            'code': f'type_a_self_{self.test_uuid}',
            'type_category': 'other',
        })

        with self.assertRaises(ValidationError):
            type_a.write({'parent_type_id': type_a.id})

        type_a.unlink()

    def test_parent_child_relationship(self):
        """Parent-child relationship works correctly."""
        parent = self.ContactType.create({
            'name': 'Parent Type',
            'code': f'parent_test_{self.test_uuid}',
            'type_category': 'other',
        })
        child = self.ContactType.create({
            'name': 'Child Type',
            'code': f'child_test_{self.test_uuid}',
            'type_category': 'other',
            'parent_type_id': parent.id,
        })

        self.assertEqual(child.parent_type_id, parent)
        self.assertIn(child, parent.child_ids)

        child.unlink()
        parent.unlink()

    def test_contact_type_creation(self):
        """Basic contact type creation works."""
        ct = self.ContactType.create({
            'name': 'Test Type',
            'code': f'test_type_{self.test_uuid}',
            'type_category': 'other',
            'sequence': 100,
            'description': 'Test description',
        })

        self.assertEqual(ct.name, 'Test Type')
        self.assertEqual(ct.code, f'test_type_{self.test_uuid}')
        self.assertEqual(ct.type_category, 'other')
        self.assertEqual(ct.sequence, 100)
        self.assertTrue(ct.active)

        ct.unlink()

    def test_contact_type_archiving(self):
        """Contact types can be archived."""
        ct = self.ContactType.create({
            'name': 'Archivable Type',
            'code': f'archivable_type_{self.test_uuid}',
            'type_category': 'other',
        })

        self.assertTrue(ct.active)
        ct.write({'active': False})
        self.assertFalse(ct.active)

        active_types = self.ContactType.search([
            ('code', '=', f'archivable_type_{self.test_uuid}'),
        ])
        self.assertNotIn(ct, active_types)

        all_types = self.ContactType.with_context(active_test=False).search([
            ('code', '=', f'archivable_type_{self.test_uuid}'),
        ])
        self.assertIn(ct, all_types)

        ct.unlink()

    @mute_logger('odoo.sql_db', 'odoo.orm')
    def test_required_fields(self):
        """Required fields are enforced."""
        unique_suffix = uuid.uuid4().hex[:8]
        code_without_name = f'no_name_test_{unique_suffix}'
        initial_count = self.ContactType.search_count([('code', '=', code_without_name)])

        savepoint = self.env.cr.savepoint()
        record = None
        try:
            record = self.ContactType.create({
                'code': code_without_name,
                'type_category': 'other',
            })
            self.env.flush_all()
            savepoint.rollback()
            if record and record.exists():
                record.unlink()
            self.fail("Creating contact type without 'name' should have failed")
        except Exception:  # noqa: BLE001
            savepoint.rollback()

        final_count = self.ContactType.search_count([('code', '=', code_without_name)])
        self.assertEqual(final_count, initial_count)

    def test_company_id_field(self):
        """company_id field works for multi-company support."""
        global_type = self.ContactType.create({
            'name': 'Global Type',
            'code': f'global_type_{self.test_uuid}',
            'type_category': 'other',
        })
        self.assertFalse(global_type.company_id)

        company = self.env['res.company'].search([], limit=1)
        if company:
            company_type = self.ContactType.create({
                'name': 'Company Type',
                'code': f'company_type_{self.test_uuid}',
                'type_category': 'other',
                'company_id': company.id,
            })
            self.assertEqual(company_type.company_id, company)
            company_type.unlink()

        global_type.unlink()

    def test_child_ids_computed_field(self):
        """child_ids One2many field works correctly."""
        if self.creator_type:
            artist = self.ContactType.search([
                ('code', '=', 'artist'),
                ('parent_type_id', '=', self.creator_type.id),
            ], limit=1)

            if artist:
                self.assertIn(artist, self.creator_type.child_ids)

                designer = self.ContactType.create({
                    'name': 'Designer Test',
                    'code': f'designer_test_child_{self.test_uuid}',
                    'type_category': 'creator',
                    'parent_type_id': self.creator_type.id,
                })
                self.assertIn(designer, self.creator_type.child_ids)
                designer.unlink()

    def test_contact_type_search(self):
        """Searching contact types by code, name, category works."""
        creator = self.ContactType.search([('code', '=', 'creator')], limit=1)
        self.assertTrue(creator)

        creator_by_name = self.ContactType.search([('name', 'ilike', 'Creator')], limit=1)
        self.assertTrue(creator_by_name)

        creator_types = self.ContactType.search([('type_category', '=', 'creator')])
        self.assertTrue(creator_types)

        artist = self.ContactType.search([
            ('code', '=', 'artist'),
            ('parent_type_id', '!=', False),
        ], limit=1)
        if artist:
            self.assertTrue(artist.parent_type_id)

    def test_contact_type_domain_filtering(self):
        """Domain filtering for parent types only works."""
        parent_types = self.ContactType.search([('parent_type_id', '=', False)])
        self.assertTrue(parent_types)
        for parent in parent_types:
            self.assertFalse(parent.parent_type_id)

        subtypes = self.ContactType.search([('parent_type_id', '!=', False)])
        if subtypes:
            for subtype in subtypes:
                self.assertTrue(subtype.parent_type_id)

    # ==========================================
    # New hierarchy tests (Story 02)
    # ==========================================

    def test_creator_type_initialized(self):
        """Creator parent type has correct code and category."""
        self.assertTrue(self.creator_type, "Creator type should be initialized")
        self.assertEqual(self.creator_type.code, 'creator')
        self.assertEqual(self.creator_type.type_category, 'creator')
        self.assertFalse(self.creator_type.parent_type_id)

    def test_contact_type_initialized(self):
        """Contact parent type has correct code and category (formerly Customer)."""
        self.assertTrue(self.contact_type, "Contact type should be initialized")
        self.assertEqual(self.contact_type.code, 'contact')
        self.assertEqual(self.contact_type.type_category, 'contact')
        self.assertFalse(self.contact_type.parent_type_id)

    def test_customer_type_absent(self):
        """Customer type no longer exists (renamed to Contact)."""
        customer_type = self.ContactType.search([('code', '=', 'customer')])
        self.assertFalse(customer_type, "Customer type should have been renamed to Contact")

    def test_artist_subtype_initialized(self):
        """Artist is a sub-type of Creator with correct category."""
        artist = self.ContactType.search([
            ('code', '=', 'artist'),
            ('parent_type_id', '!=', False),
        ], limit=1)

        if self.creator_type and artist:
            self.assertEqual(artist.parent_type_id, self.creator_type)
            self.assertEqual(artist.type_category, 'creator')

    def test_contact_subtypes_initialized(self):
        """Bidder, Buyer, Consignor, Donor, Lender are sub-types of Contact."""
        expected_codes = ['bidder', 'buyer', 'consignor', 'donor', 'lender']
        for code in expected_codes:
            subtype = self.ContactType.search([('code', '=', code)], limit=1)
            self.assertTrue(subtype, f"Contact sub-type '{code}' should be initialized")
            self.assertEqual(
                subtype.parent_type_id,
                self.contact_type,
                f"'{code}' should be a sub-type of Contact",
            )
            self.assertEqual(subtype.type_category, 'contact')

    def test_removed_types_absent(self):
        """Removed types are absent from active records."""
        removed_codes = ['private_collector', 'corporate_collector', 'institutions_collection', 'dealer', 'advisor']
        types = self.ContactType.search([('code', 'in', removed_codes)])
        self.assertFalse(types, f"Removed types should be archived; found active: {types.mapped('code')}")

    def test_only_two_parent_types_exist(self):
        """Exactly two parent types exist: Creator and Contact."""
        parent_types = self.ContactType.search([('parent_type_id', '=', False)])
        parent_codes = set(parent_types.mapped('code'))
        self.assertEqual(
            parent_codes,
            {'creator', 'contact'},
            f"Expected only Creator and Contact parent types; found: {parent_codes}",
        )

    def test_contact_types_are_global(self):
        """Seeded contact types are global (company_id=False)."""
        seeded_codes = ['creator', 'artist', 'contact', 'bidder', 'buyer', 'consignor', 'donor', 'lender']
        for code in seeded_codes:
            ct = self.ContactType.search([('code', '=', code)], limit=1)
            if ct:
                self.assertFalse(
                    ct.company_id,
                    f"Seeded type '{code}' should be global (company_id=False)",
                )

    def test_type_category_contact_valid(self):
        """type_category 'contact' is a valid selection value."""
        ct = self.ContactType.create({
            'name': 'Test Contact Category',
            'code': f'test_contact_cat_{self.test_uuid}',
            'type_category': 'contact',
        })
        self.assertEqual(ct.type_category, 'contact')
        ct.unlink()

    def test_type_category_customer_invalid(self):
        """type_category 'customer' is no longer a valid selection value."""
        with self.assertRaises(Exception):
            ct = self.ContactType.create({
                'name': 'Test Customer Category',
                'code': f'test_customer_cat_{self.test_uuid}',
                'type_category': 'customer',
            })
            self.env.flush_all()
            ct.unlink()
