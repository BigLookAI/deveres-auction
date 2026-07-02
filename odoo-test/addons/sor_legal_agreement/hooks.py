def post_init_hook(env):
    """Create a company-specific agreement sequence for every existing company.

    The main company sequence is created by the data XML. This hook covers all
    other companies that exist at install time and skips any that already have
    a sequence (including main_company).
    """
    for company in env['res.company'].search([]):
        _ensure_agreement_sequence(env, company)


def _ensure_agreement_sequence(env, company):
    existing = env['ir.sequence'].search([
        ('code', '=', 'sor.agreement'),
        ('company_id', '=', company.id),
    ])
    if not existing:
        env['ir.sequence'].create({
            'name': f'SOR Agreement ({company.name})',
            'code': 'sor.agreement',
            'prefix': 'AGR/%(year)s/',
            'padding': 5,
            'number_increment': 1,
            'number_next': 1,
            'company_id': company.id,
        })
