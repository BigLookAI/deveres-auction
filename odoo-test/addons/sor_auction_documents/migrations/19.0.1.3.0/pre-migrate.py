import logging

_logger = logging.getLogger(__name__)

_MODULE = 'sor_auction_documents'
_STALE_VIEW_NAMES = ('view_sor_event_form_inherit_posa_send_button',)


def _collect_descendants(cr, parent_ids):
    """Return all view IDs that descend from parent_ids (any depth)."""
    if not parent_ids:
        return []
    cr.execute('SELECT id FROM ir_ui_view WHERE inherit_id = ANY(%s)', (parent_ids,))
    children = [row[0] for row in cr.fetchall()]
    return children + _collect_descendants(cr, children)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = %s AND name = ANY(%s) AND res_id IS NOT NULL
    """, (_MODULE, list(_STALE_VIEW_NAMES)))
    view_ids = [row[0] for row in cr.fetchall()]
    if not view_ids:
        return

    # Delete descendant (child) views first — the ir_ui_view_inheritance_mode
    # CHECK constraint in Odoo 19 prevents setting inherit_id = NULL on
    # extension-mode child views, so the old NULL-then-delete pattern raises
    # psycopg2.errors.CheckViolation when a stale view has children.
    descendant_ids = _collect_descendants(cr, view_ids)
    if descendant_ids:
        cr.execute('DELETE FROM ir_ui_view_group_rel WHERE view_id = ANY(%s)', (descendant_ids,))
        cr.execute('DELETE FROM ir_ui_view WHERE id = ANY(%s)', (descendant_ids,))

    cr.execute('DELETE FROM ir_ui_view_group_rel WHERE view_id = ANY(%s)', (view_ids,))
    cr.execute('DELETE FROM ir_ui_view WHERE id = ANY(%s)', (view_ids,))
    cr.execute('DELETE FROM ir_model_data WHERE module = %s AND name = ANY(%s)',
               (_MODULE, list(_STALE_VIEW_NAMES)))

    _logger.info(
        'sor_auction_documents 19.0.1.3.0 pre-migrate: removed %d stale view record(s) '
        '(dead event-level POSA send button, deleted per Sprint Findings SP01)',
        len(view_ids),
    )
