import logging

_logger = logging.getLogger(__name__)

_YEAR_COLS = ('birth_year', 'death_year')


def migrate(cr, version):
    if not version:
        return
    for col in _YEAR_COLS:
        cr.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'res_partner' AND column_name = %s",
            (col,),
        )
        row = cr.fetchone()
        if row and row[0] in ('integer', 'bigint'):
            _logger.info(
                'sor_contact_roles: converting res_partner.%s from INTEGER to varchar',
                col,
            )
            # col is a hardcoded constant — f-string is safe here.
            # Valid years (1000-2099) are cast to text; 0 and out-of-range values become NULL.
            cr.execute(
                f"ALTER TABLE res_partner ALTER COLUMN {col} TYPE varchar "
                f"USING CASE WHEN {col} BETWEEN 1000 AND 2099 THEN {col}::text ELSE NULL END",
            )
