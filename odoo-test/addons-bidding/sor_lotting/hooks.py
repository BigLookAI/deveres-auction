def post_init_hook(env):
    for company in env['res.company'].search([]):
        _ensure_lot_sequence(env, company)


def _ensure_lot_sequence(env, company):
    existing = env['ir.sequence'].search([
        ('code', '=', 'sor.lot'),
        ('company_id', '=', company.id),
    ])
    if not existing:
        env['ir.sequence'].create({
            'name': f'SOR Lot ({company.name})',
            'code': 'sor.lot',
            'prefix': 'LOT/%(year)s/',
            'padding': 5,
            'number_increment': 1,
            'number_next': 1,
            'company_id': company.id,
        })


def post_migrate(env, version):
    if not version:
        return
    # sor_lotting has no production data — no data migration required.
    pass
