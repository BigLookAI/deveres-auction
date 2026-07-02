import logging

_logger = logging.getLogger(__name__)

# View xmlids whose arch contains 'has_customer_type' (renamed to 'has_contact_type').
# These records must be deleted before data files are loaded so that combined arch
# validation does not fail on the removed field name.
_STALE_VIEW_NAMES = (
    'view_partner_form_inherit_contact_types',
    'view_partner_form_inherit_customer_fields',
)


def migrate(cr, version):
    """Pre-migrate: remove stale view records that reference the renamed field has_customer_type."""
    if not version:
        return

    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'sor_contact_roles'
          AND name = ANY(%s)
          AND res_id IS NOT NULL
    """, (list(_STALE_VIEW_NAMES),))
    view_ids = [row[0] for row in cr.fetchall()]

    if view_ids:
        # Delete any group assignments on those views
        cr.execute(
            "DELETE FROM ir_ui_view_group_rel WHERE view_id = ANY(%s)",
            (view_ids,),
        )
        # Nullify inherit_id on any child patches (safety — should be none for patch views)
        cr.execute(
            "UPDATE ir_ui_view SET inherit_id = NULL WHERE inherit_id = ANY(%s)",
            (view_ids,),
        )
        cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", (view_ids,))
        _logger.info(
            'sor_contact_roles pre-migrate 19.0.1.2.0: deleted %d stale view records '
            'referencing has_customer_type',
            len(view_ids),
        )

    # Remove model data entries so data files recreate them fresh
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'sor_contact_roles'
          AND name = ANY(%s)
    """, (list(_STALE_VIEW_NAMES),))
    _logger.info(
        'sor_contact_roles pre-migrate 19.0.1.2.0: removed %d ir_model_data entries',
        cr.rowcount,
    )
