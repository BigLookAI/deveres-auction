# ── LOCAL 19.0.1.7.0 RECONSTRUCTION (Cimelium, 2-Jul-2026) ────────────────────
# The April-test database was created by sor_contact_roles 19.0.1.7.0; available
# source is 19.0.1.5.0. 1.6/1.7 added the creator lifecycle years, referenced by
# the artist list and creator form views stored in the database.
from odoo import fields, models


class ResPartnerV170(models.Model):
    _inherit = 'res.partner'

    birth_year = fields.Char(string='Birth Year')
    death_year = fields.Char(string='Death Year')
