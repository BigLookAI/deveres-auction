def post_init_hook(env):
    _enable_serial_tracking(env)
    _migrate_existing_artworks(env)
    for company in env['res.company'].search([]):
        _ensure_serial_sequence(env, company)


def _enable_serial_tracking(env):
    settings = env['res.config.settings'].create({})
    settings.group_stock_production_lot = True
    settings.group_lot_on_delivery_slip = True
    settings.execute()


def _migrate_existing_artworks(env):
    artwork_products = env['product.template'].search([('product_type', '=', 'artwork')])
    if artwork_products:
        artwork_products.write({'tracking': 'serial'})


def _ensure_serial_sequence(env, company):
    existing = env['ir.sequence'].search([
        ('code', '=', 'sor.artwork.serial'),
        ('company_id', '=', company.id),
    ])
    if not existing:
        env['ir.sequence'].create({
            'name': f'SOR Artwork Serial Number ({company.name})',
            'code': 'sor.artwork.serial',
            'prefix': 'SN/%(year)s/',
            'padding': 5,
            'number_increment': 1,
            'number_next': 1,
            'company_id': company.id,
        })
