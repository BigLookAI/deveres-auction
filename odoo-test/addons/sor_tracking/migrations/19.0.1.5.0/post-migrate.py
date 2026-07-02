import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Archive Partner/External locations left over from sor_tracking < 19.0.1.4.0.

    Earlier versions of sor_tracking provisioned a 'Partner/External' location
    (usage=supplier) per company. Finding 5 (Show & Tell) established that these
    duplicate sor_locations_external infrastructure and should not exist. This
    migration archives them so they no longer appear in location dropdowns.

    Only locations with no stock move references are archived — locations that
    were actually used are left active to preserve referential integrity.
    """
    cr.execute("""
        SELECT l.id
        FROM stock_location l
        WHERE l.name = 'Partner/External'
          AND l.usage = 'supplier'
          AND l.complete_name LIKE '%Partner/External%'
          AND NOT EXISTS (
              SELECT 1 FROM stock_move
              WHERE location_id = l.id OR location_dest_id = l.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM stock_move_line
              WHERE location_id = l.id OR location_dest_id = l.id
          )
    """)
    location_ids = [row[0] for row in cr.fetchall()]
    if location_ids:
        cr.execute(
            "UPDATE stock_location SET active = FALSE WHERE id = ANY(%s)",
            (location_ids,),
        )
        _logger.info(
            "sor_tracking 19.0.1.5.0: archived %d Partner/External location(s) with id(s) %s",
            len(location_ids),
            location_ids,
        )
    else:
        _logger.info(
            "sor_tracking 19.0.1.5.0: no unused Partner/External locations found to archive",
        )
