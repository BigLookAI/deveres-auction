def post_init_hook(env):
    """Retroactively assign Consignor sub-type to all partners already set as consignor_id."""
    lots_with_consignors = env['sor.lot'].search([('consignor_id', '!=', False)])
    for lot in lots_with_consignors:
        lot._assign_consignor_subtype()
