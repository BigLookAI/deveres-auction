import logging

_logger = logging.getLogger(__name__)

# view_partner_form_inherit_creator_fields referenced birth_date which was
# replaced by birth_year and death_year in this release. Delete the stale DB
# record so the view validator doesn't see birth_date in the combined arch
# while the Python model no longer has that field.
_STALE_VIEWS = ('view_partner_form_inherit_creator_fields',)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'sor_contact_roles' AND name = ANY(%s) AND res_id IS NOT NULL
    """, (list(_STALE_VIEWS),))
    view_ids = [row[0] for row in cr.fetchall()]
    if not view_ids:
        return
    _logger.info('sor_contact_roles pre-migrate: removing stale views %s', view_ids)
    cr.execute("DELETE FROM ir_ui_view_group_rel WHERE view_id = ANY(%s)", (view_ids,))
    cr.execute("UPDATE ir_ui_view SET inherit_id = NULL WHERE inherit_id = ANY(%s)", (view_ids,))
    cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", (view_ids,))
    cr.execute(
        "DELETE FROM ir_model_data WHERE module = 'sor_contact_roles' AND name = ANY(%s)",
        (list(_STALE_VIEWS),),
    )
