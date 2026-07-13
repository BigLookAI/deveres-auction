import logging

_logger = logging.getLogger(__name__)

# report_invoice_document_sor_buyer_invoice changed from an inherit_id-based extension
# of account.report_invoice_document to a fully standalone (no inherit_id) template.
# The existing DB record still carries the stale inherit_id, which makes Odoo try to
# locate the new standalone content inside the old parent's arch and raise
# "Element ... cannot be located in parent view". Delete the stale view (and its
# descendant, the sor_buyer_invoice_auction_house bridge template, which inherits from
# it) before data files reload, so both are recreated fresh with no stale inherit_id.
_STALE_VIEWS = (
    ('sor_buyer_invoice', 'report_invoice_document_sor_buyer_invoice'),
    ('sor_buyer_invoice_auction_house', 'report_invoice_document_sor_auction_house_bridge'),
)


def _collect_descendants(cr, parent_ids):
    if not parent_ids:
        return []
    cr.execute('SELECT id FROM ir_ui_view WHERE inherit_id = ANY(%s)', (parent_ids,))
    children = [row[0] for row in cr.fetchall()]
    return children + _collect_descendants(cr, children)


def migrate(cr, version):
    if not version:
        return

    view_ids = []
    for module, name in _STALE_VIEWS:
        cr.execute("""
            SELECT res_id FROM ir_model_data
            WHERE module = %s AND name = %s AND res_id IS NOT NULL
        """, (module, name))
        view_ids.extend(row[0] for row in cr.fetchall())
    if not view_ids:
        return

    descendant_ids = _collect_descendants(cr, view_ids)
    all_ids = list(set(descendant_ids) | set(view_ids))

    cr.execute('DELETE FROM ir_ui_view_group_rel WHERE view_id = ANY(%s)', (all_ids,))
    cr.execute('DELETE FROM ir_ui_view WHERE id = ANY(%s)', (all_ids,))
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.ui.view' AND res_id = ANY(%s)
    """, (all_ids,))
    _logger.info('sor_buyer_invoice pre-migrate: deleted %d stale view(s) prior to reload', len(all_ids))
