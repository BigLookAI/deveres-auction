import logging

_logger = logging.getLogger(__name__)


def _find_income_account(env, company):
    """Return the first income account associated with the given company, or empty recordset.

    In Odoo 19, account.account uses a company_ids Many2many (account_account_res_company_rel)
    rather than a simple company_id field.  ORM domain filters on company_id / company_ids are
    not reliably available across all installation contexts, so we use a targeted SQL lookup.
    """
    env.cr.execute(
        """
        SELECT a.id
        FROM account_account a
        JOIN account_account_res_company_rel r ON r.account_account_id = a.id
        WHERE a.account_type = 'income'
          AND r.res_company_id = %s
        ORDER BY a.id
        LIMIT 1
        """,
        (company.id,),
    )
    row = env.cr.fetchone()
    return env['account.account'].browse(row[0]) if row else env['account.account'].browse()


def _ensure_auction_journal(env, company):
    """Provision an Auction Sales journal for the given company if absent.

    Sets default_account_id to the company's primary income account so that
    _prepare_buyer_invoice_lines can fall back to the journal account when no
    explicit account is set on an invoice line.
    """
    existing = env['account.journal'].sudo().search([
        ('code', '=', 'AUC'),
        ('company_id', '=', company.id),
    ])
    income_account = _find_income_account(env, company)
    if not existing:
        journal_vals = {
            'name': 'Auction Sales',
            'type': 'sale',
            'code': 'AUC',
            'company_id': company.id,
            'invoice_reference_type': 'invoice',
            'invoice_reference_model': 'odoo',
        }
        if income_account:
            journal_vals['default_account_id'] = income_account.id
        env['account.journal'].sudo().create(journal_vals)
    elif not existing.default_account_id and income_account:
        # Journal exists but default account was not set at creation time
        # (e.g. chart of accounts had not been applied yet).
        existing.sudo().write({'default_account_id': income_account.id})


def _ensure_auction_payment_methods(env, company):
    """Provision the four auction payment methods on the company's Bank journal, if absent.

    Each line's payment_account_id is set explicitly to the journal's own default
    account (reconcile=False in this codebase's chart) — Odoo's UI default for a
    manually-created line is Outstanding Receipts (reconcile=True), which is what
    causes a registered payment to stay "In Process" indefinitely instead of
    posting straight to Paid. This is applied going forward only: a company that
    already has lines under these names (e.g. manually configured before this
    story) is left untouched.
    """
    journal = env['account.journal'].sudo().search([
        ('company_id', '=', company.id),
        ('type', '=', 'bank'),
    ], limit=1)
    if not journal:
        return

    manual_in = env.ref('account.account_payment_method_manual_in')
    existing_names = set(journal.inbound_payment_method_line_ids.mapped('name'))
    for label in ('Debit Card', 'Bank Transfer', 'Cheque', 'Bank Draft'):
        if label in existing_names:
            continue
        env['account.payment.method.line'].sudo().create({
            'name': label,
            'payment_method_id': manual_in.id,
            'journal_id': journal.id,
            'payment_account_id': journal.default_account_id.id,
        })


def _ensure_buyer_invoice_sequence(env, company):
    """Provision a per-company buyer invoice sequence if absent."""
    existing = env['ir.sequence'].search([
        ('code', '=', 'sor.buyer.invoice'),
        ('company_id', '=', company.id),
    ])
    if not existing:
        env['ir.sequence'].create({
            'name': f'Buyer Invoice ({company.name})',
            'code': 'sor.buyer.invoice',
            'prefix': '',
            'padding': 6,
            'number_increment': 1,
            'number_next': 1,
            'use_date_range': False,
            'company_id': company.id,
        })


def post_init_hook(env):
    _logger.info('sor_buyer_invoice_auction_house post_init_hook: starting')
    for company in env['res.company'].search([]):
        _ensure_auction_journal(env, company)
        _ensure_auction_payment_methods(env, company)
        _ensure_buyer_invoice_sequence(env, company)
    _logger.info('sor_buyer_invoice_auction_house post_init_hook: complete')
