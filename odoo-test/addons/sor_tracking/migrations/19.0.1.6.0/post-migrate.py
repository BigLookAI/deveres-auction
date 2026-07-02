def migrate(cr, version):
    if not version:
        return
    # Reset the noupdate=1 stock.menu_stock_root record that was set to active=False
    # by the data XML in sor_tracking (now removed). Odoo never resets noupdate=1
    # records on upgrade regardless of whether they remain in XML, so raw SQL is
    # required. The sor_artwork post_init_hook will re-suppress when appropriate.
    cr.execute("""
        UPDATE ir_ui_menu SET active = TRUE
        WHERE id = (
            SELECT res_id FROM ir_model_data
            WHERE module = 'stock' AND name = 'menu_stock_root' LIMIT 1
        )
    """)
