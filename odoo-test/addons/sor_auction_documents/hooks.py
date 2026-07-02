def _ensure_vss_sequence(env, company):
    Sequence = env['ir.sequence'].sudo()
    existing = Sequence.search([
        ('code', '=', 'sor.vendor.settlement'),
        ('company_id', '=', company.id),
    ])
    if not existing:
        Sequence.create({
            'name': f'SOR Vendor Settlement Statement ({company.name})',
            'code': 'sor.vendor.settlement',
            'padding': 6,
            'number_increment': 1,
            'number_next': 100001,
            'company_id': company.id,
        })


def post_init_hook(env):
    for company in env['res.company'].sudo().search([]):
        _ensure_vss_sequence(env, company)
