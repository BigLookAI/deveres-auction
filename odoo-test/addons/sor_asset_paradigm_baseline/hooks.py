def post_init_hook(env):
    """Create the Baseline Product via ORM to avoid column dependencies on optional modules.

    The original SQL INSERT included `product_type` (added by sor_artwork), causing
    fresh-install failures in environments without sor_artwork. The ORM create omits
    optional columns safely — fields not passed receive their model defaults.
    """
    existing = env['ir.model.data'].search([
        ('module', '=', 'sor_asset_paradigm_baseline'),
        ('name', '=', 'baseline_product'),
    ])
    if existing:
        return

    uom = env.ref('uom.product_uom_unit', raise_if_not_found=False)
    if not uom:
        uom = env['uom.uom'].search([], limit=1)
    if not uom:
        return

    product = env['product.template'].sudo().with_context(
        default_product_type=False,
    ).create({
        'name': 'Baseline Product (SOR Paradigm Reference)',
        'type': 'consu',
        'is_storable': True,
        'asset_paradigm': 'standard',
        'active': False,
        'uom_id': uom.id,
        'service_tracking': 'no',
        'tracking': 'none',
    })

    env['ir.model.data'].sudo().create({
        'module': 'sor_asset_paradigm_baseline',
        'name': 'baseline_product',
        'model': 'product.template',
        'res_id': product.id,
        'noupdate': True,
    })
