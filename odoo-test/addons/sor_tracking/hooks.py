def post_init_hook(env):
    _enable_settings(env)
    for company in env['res.company'].search([]):
        _ensure_pool_locations(env, company)


def _enable_settings(env):
    settings = env['res.config.settings'].create({})
    settings.group_stock_multi_locations = True
    settings.group_stock_tracking_owner = True
    settings.execute()


def _ensure_pool_locations(env, company):
    Location = env['stock.location'].sudo()

    # Company-scoped External view location — no global virtual root in Odoo 19
    external = Location.search([
        ('name', '=', 'External'),
        ('usage', '=', 'view'),
        ('company_id', '=', company.id),
    ], limit=1)
    if not external:
        external = Location.create({
            'name': 'External',
            'usage': 'view',
            'company_id': company.id,
            'location_id': False,
        })

    pool_locations = [
        ('Partners/External', 'internal'),
        ('Vendors/External', 'supplier'),
        ('Buyers/External', 'customer'),
    ]
    for name, usage in pool_locations:
        existing = Location.search([
            ('name', '=', name),
            ('usage', '=', usage),
            ('company_id', '=', company.id),
            ('location_id', '=', external.id),
        ], limit=1)
        if not existing:
            Location.create({
                'name': name,
                'usage': usage,
                'company_id': company.id,
                'location_id': external.id,
            })
