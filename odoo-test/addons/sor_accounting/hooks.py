import logging

from odoo.addons.sor_technical_menu.utils import (
    set_menu_developer_only,
    set_menu_unrestricted,
)

_logger = logging.getLogger(__name__)

# GL/reporting surfaces restricted to developer mode only.
# Staff see: Invoicing → Customers → [Invoices, Credit Notes, Payments, Products, Customers]
# All listed menus cascade-hide their children automatically.
SUPPRESSED_MENUS = [
    'account.menu_board_journal_1',       # Dashboard
    'account.menu_finance_payables',      # Vendors
    'account.menu_finance_entries',       # Accounting (GL journal entries)
    'account.account_audit_menu',         # Review
    'account.menu_finance_reports',       # Reporting
    'account.menu_finance_configuration',  # Configuration
]


def post_init_hook(env):
    _logger.info('sor_accounting post_init_hook: starting')
    for xmlid in SUPPRESSED_MENUS:
        set_menu_developer_only(env, xmlid)
    _logger.info('sor_accounting post_init_hook: complete')


def uninstall_hook(env):
    for xmlid in SUPPRESSED_MENUS:
        set_menu_unrestricted(env, xmlid)
