import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # auction_vat_notice was converted from plain Text to Html in this version.
    # Existing content used bare newlines for line breaks, which HTML does not
    # render as line breaks — convert them to <br/> so existing wording (e.g.
    # deVeres's statutory VAT notice) keeps its visual formatting.
    cr.execute("""
        UPDATE res_company
        SET auction_vat_notice = REPLACE(auction_vat_notice, E'\n', '<br/>' || E'\n')
        WHERE auction_vat_notice IS NOT NULL
          AND auction_vat_notice != ''
    """)
    _logger.info(
        "sor_commercial_auction_house: converted newlines to <br/> in auction_vat_notice "
        "for %s companies",
        cr.rowcount,
    )
