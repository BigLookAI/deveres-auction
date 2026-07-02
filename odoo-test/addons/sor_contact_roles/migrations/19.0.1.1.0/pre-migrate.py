import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Pre-migrate: archive 'buyer' contact type and unlink from partners."""
    if not version:
        return

    # Unlink 'buyer' contact type from all partner contact_subtypes M2M
    cr.execute("""
        DELETE FROM sor_contact_subtype_res_partner_rel
        WHERE contact_type_id IN (
            SELECT id FROM sor_contact_type WHERE code = 'buyer'
        )
    """)
    removed_subtypes = cr.rowcount
    _logger.info("Removed %d buyer subtype assignments from partners.", removed_subtypes)

    # Unlink 'buyer' contact type from all partner contact_types M2M
    cr.execute("""
        DELETE FROM sor_contact_type_res_partner_rel
        WHERE contact_type_id IN (
            SELECT id FROM sor_contact_type WHERE code = 'buyer'
        )
    """)
    removed_types = cr.rowcount
    _logger.info("Removed %d buyer type assignments from partners.", removed_types)

    # Archive the 'buyer' contact type record (set active=False)
    cr.execute("""
        UPDATE sor_contact_type SET active = FALSE WHERE code = 'buyer'
    """)
    archived = cr.rowcount
    _logger.info("Archived %d buyer contact type record(s).", archived)
