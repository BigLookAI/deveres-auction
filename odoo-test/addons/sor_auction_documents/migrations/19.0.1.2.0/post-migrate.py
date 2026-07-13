import logging

from markupsafe import Markup, escape

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _text_to_html(text):
    """Convert a plain-text field's value into a safe HTML paragraph."""
    if not text:
        return ''
    lines = [escape(line) for line in text.split('\n')]
    return Markup('<p>%s</p>') % Markup('<br/>').join(lines)


def migrate(cr, version):
    if not version:
        return

    # auction_sale_terms / auction_bank_details / auction_licence_ref /
    # auction_director_signature are removed from the model in this version —
    # read them via raw SQL before the ORM no longer exposes the field names.
    cr.execute("""
        SELECT id, auction_sale_terms, auction_bank_details,
               auction_licence_ref, auction_director_signature
        FROM res_company
    """)
    rows = cr.fetchall()
    if not rows:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    migrated = 0
    for company_id, sale_terms, bank_details, licence_ref, director_signature in rows:
        if not any([sale_terms, bank_details, licence_ref, director_signature]):
            continue

        sale_terms_html = Markup(sale_terms) if sale_terms else Markup('')
        bank_details_html = Markup(_text_to_html(bank_details))
        vss_bottom = bank_details_html + sale_terms_html

        footer_parts = []
        if licence_ref:
            footer_parts.append(Markup('<p>%s</p>') % escape(licence_ref))
        if director_signature:
            footer_parts.append(Markup(_text_to_html(director_signature)))
        footer_html = Markup('').join(footer_parts)

        vals = {}
        if sale_terms:
            vals['psa_content_bottom'] = sale_terms_html
            vals['posa_content_bottom'] = sale_terms_html
        if bank_details or sale_terms:
            vals['vss_content_bottom'] = vss_bottom

        company = env['res.company'].browse(company_id)
        if licence_ref or director_signature:
            # auction_document_footer was dropped in favour of Odoo's native,
            # already-per-page-footer-rendering company.report_footer field —
            # append rather than overwrite any pre-existing footer content.
            existing_footer = company.report_footer or Markup('')
            vals['report_footer'] = existing_footer + footer_html

        if vals:
            company.write(vals)
            migrated += 1

    _logger.info(
        'sor_auction_documents 19.0.1.2.0 migration: carried forward content for %d compan%s',
        migrated, 'y' if migrated == 1 else 'ies',
    )
