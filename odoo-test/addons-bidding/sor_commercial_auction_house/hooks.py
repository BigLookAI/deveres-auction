_FEE_DEFAULTS = [
    ('sellers_commission', 0.0),
    ('withdrawal_fee', 0.0),
]


def post_init_hook(env):
    for company in env['res.company'].search([]):
        _ensure_fee_defaults(env, company)
        _ensure_buyers_premium_tier(env, company)


def _ensure_fee_defaults(env, company):
    FeeDefault = env['sor.fee.default'].sudo()
    for fee_type, rate_pct in _FEE_DEFAULTS:
        existing = FeeDefault.search([
            ('company_id', '=', company.id),
            ('fee_type', '=', fee_type),
        ])
        if not existing:
            FeeDefault.create({
                'company_id': company.id,
                'fee_type': fee_type,
                'rate_pct': rate_pct,
            })


def _ensure_buyers_premium_tier(env, company):
    Tier = env['sor.buyers.premium.tier'].sudo()
    existing = Tier.search([
        ('company_id', '=', company.id),
    ])
    if not existing:
        Tier.create({
            'company_id': company.id,
            'sequence': 10,
            'threshold_from': 0.0,
            'rate_pct': 0.0,
        })
