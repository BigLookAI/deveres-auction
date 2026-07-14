import logging

_logger = logging.getLogger(__name__)

_MODULE = 'sor_auction_documents'
_STALE_VIEW_NAMES = (
    'view_sor_lot_form_inherit_auction_docs',
    'res_config_settings_view_form_inherit_auction_docs',
    'view_sor_post_sale_advice_form',
    'view_sor_vendor_settlement_form',
)


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
    _logger.info(
        'Pre-migrating %s: removing stale view arches for vat_margin_scheme rename',
        _MODULE,
    )
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
        WHERE module = %s AND name = ANY(%s) AND res_id IS NOT NULL
        """,
        (_MODULE, list(_STALE_VIEW_NAMES)),
    )
    view_ids = [row[0] for row in cr.fetchall()]
    if not view_ids:
        _logger.info('Pre-migration complete: no stale views found')
        return

    # Delete descendant (child) views first. The ir_ui_view_inheritance_mode check
    # constraint prevents setting inherit_id = NULL on extension-mode views, so we
    # cannot use the standard NULL-then-delete pattern when stale views have children.
    # Descendants (e.g. sor_consignment_auction views that inherit our stale lot form)
    # will be recreated by their own module's XML during the upgrade run.
    descendant_ids = _collect_descendants(cr, view_ids)
    if descendant_ids:
        _logger.info(
            'Pre-migration: removing %d descendant view(s) (recreated by module XML)',
            len(descendant_ids),
        )
        cr.execute(
            'DELETE FROM ir_ui_view_group_rel WHERE view_id = ANY(%s)',
            (descendant_ids,),
        )
        cr.execute(
            'DELETE FROM ir_ui_view WHERE id = ANY(%s)', (descendant_ids,),
        )

    # Now the stale views have no children — safe to delete
    cr.execute(
        'DELETE FROM ir_ui_view_group_rel WHERE view_id = ANY(%s)', (view_ids,),
    )
    cr.execute('DELETE FROM ir_ui_view WHERE id = ANY(%s)', (view_ids,))
    cr.execute(
        'DELETE FROM ir_model_data WHERE module = %s AND name = ANY(%s)',
        (_MODULE, list(_STALE_VIEW_NAMES)),
    )
    _logger.info(
        'Pre-migration complete: %d stale view(s) removed', len(view_ids),
    )
