# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models


def post_init_hook(env):  # noqa: RUF067
    """Create the Artist Studios warehouse for all existing companies on install."""
    for company in env['res.company'].search([]):
        if not company.partner_id:
            continue  # Skip companies without an address — warehouse creation requires one
        env_co = env(context=dict(env.context, allowed_company_ids=[company.id]))
        env_co['stock.warehouse']._sor_ensure_artist_studios_warehouse()
