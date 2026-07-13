import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # Recompute sellers_commission_pct for all lots where use_custom_vendor_fee = False.
    # The field was converted from plain stored Float to computed+inverse in 19.0.1.2.0.
    # The ORM's invalidate+flush approach does not reliably trigger a DB write for stored
    # computed fields when their definition changes during upgrade — raw SQL is authoritative.

    # Level 2: consignor override applies — use consignor's custom rate
    cr.execute("""
        UPDATE sor_lot l
        SET sellers_commission_pct = p.default_sellers_commission_pct
        FROM res_partner p
        WHERE l.consignor_id = p.id
          AND l.use_custom_vendor_fee = FALSE
          AND p.use_custom_default_commission = TRUE
    """)
    level2_count = cr.rowcount
    _logger.info(
        "sor_commercial_auction_house: recomputed %s lots using consignor override (Level 2)",
        level2_count,
    )

    # Level 3: company default — consignor absent or no override
    cr.execute("""
        UPDATE sor_lot l
        SET sellers_commission_pct = COALESCE(fd.rate_pct, 0.0)
        FROM sor_fee_default fd
        WHERE fd.company_id = l.company_id
          AND fd.fee_type = 'sellers_commission'
          AND l.use_custom_vendor_fee = FALSE
          AND (
              l.consignor_id IS NULL
              OR NOT EXISTS (
                  SELECT 1 FROM res_partner p2
                  WHERE p2.id = l.consignor_id
                    AND p2.use_custom_default_commission = TRUE
              )
          )
    """)
    level3_count = cr.rowcount
    _logger.info(
        "sor_commercial_auction_house: recomputed %s lots using company default (Level 3)",
        level3_count,
    )

    # Lots with no fee default entry in the company — set to 0.0
    cr.execute("""
        UPDATE sor_lot l
        SET sellers_commission_pct = 0.0
        WHERE l.use_custom_vendor_fee = FALSE
          AND (
              l.consignor_id IS NULL
              OR NOT EXISTS (
                  SELECT 1 FROM res_partner p3
                  WHERE p3.id = l.consignor_id
                    AND p3.use_custom_default_commission = TRUE
              )
          )
          AND NOT EXISTS (
              SELECT 1 FROM sor_fee_default fd2
              WHERE fd2.company_id = l.company_id
                AND fd2.fee_type = 'sellers_commission'
          )
    """)
    _logger.info(
        "sor_commercial_auction_house: zeroed %s lots with no company fee default",
        cr.rowcount,
    )
