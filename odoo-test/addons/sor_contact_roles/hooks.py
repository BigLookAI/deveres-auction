# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Run contact type migration after module install."""
    _migrate_contact_types(env)


def _migrate_contact_types(env):
    """Migrate contact type hierarchy to the new Contact / Creator structure.

    Steps:
    1. Rename the Customer parent type record to Contact (code: customer → contact).
    2. Ensure the Contact parent type exists (handles fresh installs).
    3. Migrate Bidder from standalone parent type to Contact sub-type.
    4. Migrate Consignor from standalone parent type to Contact sub-type.
    5. Remove partner assignments to archived type records (Private Collector,
       Corporate Collector, Institutional Collector, Dealer, Advisor).
    6. Archive removed type records.
    7. Ensure new Contact sub-types (Buyer, Donor, Lender) exist.

    The migration is idempotent — running it multiple times does not duplicate
    changes or raise errors.
    """
    ContactType = env['sor.contact.type'].with_context(active_test=False)

    # 1. Rename Customer → Contact
    customer_type = ContactType.search(
        [('code', '=', 'customer'), ('parent_type_id', '=', False)],
        limit=1,
    )
    if customer_type:
        customer_type.write({
            'name': 'Contact',
            'code': 'contact',
            'type_category': 'contact',
        })
        _logger.info('sor_contact_roles: renamed Customer type → Contact')

    # 2. Ensure Contact type exists
    contact_type = ContactType.search(
        [('code', '=', 'contact'), ('parent_type_id', '=', False)],
        limit=1,
    )
    if not contact_type:
        _logger.warning(
            'sor_contact_roles: Contact parent type not found after migration step 1; '
            'fresh install may have created it via seed data.',
        )
        return

    # 3. Migrate Bidder: standalone parent → Contact sub-type
    bidder_type = ContactType.search([('code', '=', 'bidder')], limit=1)
    if bidder_type:
        # Structural migration — ensure parent_type_id is set.
        # On upgrade, the data file (noupdate=False in ir_model_data) sets parent_type_id
        # before this migration runs, so the guard may already be False. Write anyway if
        # parent is absent (covers edge cases like fresh installs without data file).
        if not bidder_type.parent_type_id:
            bidder_type.write({
                'parent_type_id': contact_type.id,
                'type_category': 'contact',
            })
        # Partner migration: use raw SQL to find stale rows in the contact_types M2M table.
        # ORM search [('contact_types', 'in', [bidder_type.id])] returns 0 because Odoo
        # applies the field's domain=[('parent_type_id', '=', False)] at search time —
        # once Bidder has a parent_type_id, the JOIN filters it out entirely.
        env.cr.execute(
            "SELECT partner_id FROM sor_contact_type_res_partner_rel WHERE contact_type_id = %s",
            (bidder_type.id,),
        )
        stale_partner_ids = [row[0] for row in env.cr.fetchall()]
        if stale_partner_ids:
            env.cr.execute(
                "DELETE FROM sor_contact_type_res_partner_rel WHERE contact_type_id = %s",
                (bidder_type.id,),
            )
            env.flush_all()
            partners = env['res.partner'].browse(stale_partner_ids)
            partners.invalidate_recordset(['contact_types', 'contact_subtypes'])
            for partner in partners:
                if bidder_type not in partner.contact_subtypes:
                    partner.contact_subtypes = [(4, bidder_type.id)]
                if contact_type not in partner.contact_types:
                    partner.contact_types = [(4, contact_type.id)]
            _logger.info(
                'sor_contact_roles: migrated %d partners: Bidder contact_types → contact_subtypes',
                len(stale_partner_ids),
            )

    # 4. Migrate activity-earned standalone parent types → Contact sub-types
    # Covers Consignor and Donor which may have existed as parent types before
    # this sprint restructured the hierarchy.
    # Uses same raw-SQL pattern as step 3 — ORM search on contact_types is blocked by
    # field domain once the type has a parent_type_id.
    for migrate_code, migrate_label in [('consignor', 'Consignor'), ('donor', 'Donor')]:
        existing = ContactType.search([('code', '=', migrate_code)], limit=1)
        if existing:
            if not existing.parent_type_id:
                existing.write({
                    'parent_type_id': contact_type.id,
                    'type_category': 'contact',
                })
            env.cr.execute(
                "SELECT partner_id FROM sor_contact_type_res_partner_rel WHERE contact_type_id = %s",
                (existing.id,),
            )
            stale_ids = [row[0] for row in env.cr.fetchall()]
            if stale_ids:
                env.cr.execute(
                    "DELETE FROM sor_contact_type_res_partner_rel WHERE contact_type_id = %s",
                    (existing.id,),
                )
                env.flush_all()
                partners = env['res.partner'].browse(stale_ids)
                partners.invalidate_recordset(['contact_types', 'contact_subtypes'])
                for partner in partners:
                    if existing not in partner.contact_subtypes:
                        partner.contact_subtypes = [(4, existing.id)]
                    if contact_type not in partner.contact_types:
                        partner.contact_types = [(4, contact_type.id)]
                _logger.info(
                    'sor_contact_roles: migrated %d partners: %s contact_types → contact_subtypes',
                    len(stale_ids),
                    migrate_label,
                )

    # 5. Remove partner assignments to removed types; 6. Archive removed types
    removed_codes = [
        'private_collector',
        'corporate_collector',
        'institutions_collection',
        'dealer',
        'advisor',
    ]
    removed_types = ContactType.search([('code', 'in', removed_codes)])
    if removed_types:
        partners_with_removed = env['res.partner'].search([
            '|',
            ('contact_types', 'in', removed_types.ids),
            ('contact_subtypes', 'in', removed_types.ids),
        ])
        for partner in partners_with_removed:
            types_to_remove = removed_types & partner.contact_types
            subtypes_to_remove = removed_types & partner.contact_subtypes
            if types_to_remove:
                partner.contact_types = [(3, t.id) for t in types_to_remove]
            if subtypes_to_remove:
                partner.contact_subtypes = [(3, t.id) for t in subtypes_to_remove]
        # Archive (not delete) to preserve referential integrity
        removed_types.write({'active': False})
        _logger.info(
            'sor_contact_roles: archived %d removed type records: %s',
            len(removed_types),
            ', '.join(removed_types.mapped('code')),
        )

    # 7. Ensure new Contact sub-types exist (Buyer, Donor, Lender)
    # These may already exist from seed data on fresh install; only create if absent.
    new_subtypes = [
        ('buyer', 'Buyer', 22),
        ('donor', 'Donor', 24),
        ('lender', 'Lender', 25),
    ]
    for code, name, sequence in new_subtypes:
        existing = ContactType.search([('code', '=', code)], limit=1)
        if not existing:
            ContactType.create({
                'name': name,
                'code': code,
                'type_category': 'contact',
                'parent_type_id': contact_type.id,
                'sequence': sequence,
                'active': True,
            })
            _logger.info('sor_contact_roles: created new Contact sub-type: %s', code)
