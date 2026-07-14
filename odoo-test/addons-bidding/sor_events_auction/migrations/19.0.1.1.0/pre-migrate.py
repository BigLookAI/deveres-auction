import logging

_logger = logging.getLogger(__name__)

_MODULE = 'sor_events_auction'
_STALE_VIEW_NAMES = (
    'sor_lot_view_form_auction_id',
    'sor_event_view_form_auction_tab',
)


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

    # These two views still reference lot_suffix (removed in this version).
    # Odoo's view validator rejects the stale arch before this module's own
    # data file can overwrite it, so delete first and let the data file
    # recreate them with the corrected arch.
    cr.execute('DELETE FROM ir_ui_view_group_rel WHERE view_id = ANY(%s)', (view_ids,))
    cr.execute('DELETE FROM ir_ui_view WHERE id = ANY(%s)', (view_ids,))
    cr.execute('DELETE FROM ir_model_data WHERE module = %s AND name = ANY(%s)',
               (_MODULE, list(_STALE_VIEW_NAMES)))
