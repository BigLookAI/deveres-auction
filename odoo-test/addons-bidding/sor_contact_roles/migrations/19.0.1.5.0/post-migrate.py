import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.sor_contact_roles.hooks import _migrate_contact_types

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Fix stale contact_types M2M rows for Bidder, Consignor, Donor.

    The 19.0.1.4.0 migration skipped partner reassignment because the ORM search
    [('contact_types', 'in', [type_id])] returns 0 after the type gains a parent_type_id
    (the field domain [('parent_type_id', '=', False)] is applied at search time).
    This version re-runs the migration using raw SQL to find and move stale rows.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _migrate_contact_types(env)
