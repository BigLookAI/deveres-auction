# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models


def post_init_hook(env):  # noqa: RUF067
    """Create the External Locations parent location for all existing companies on install."""
    for company in env['res.company'].search([]):
        env_co = env(context=dict(env.context, allowed_company_ids=[company.id]))
        env_co['stock.location']._sor_ensure_external_locations_parent()
