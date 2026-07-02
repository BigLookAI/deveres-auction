import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.sor_contact_roles.hooks import _migrate_contact_types

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Run contact type hierarchy migration for existing installations."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _migrate_contact_types(env)
