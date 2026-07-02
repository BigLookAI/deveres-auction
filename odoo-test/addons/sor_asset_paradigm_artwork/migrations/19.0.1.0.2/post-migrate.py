"""Backfill is_storable = True on artwork products.
Artwork products must be inventory-tracked (storable) so that stock stat buttons
(Forecast, Reorder Rules, etc.) are available to suppress via paradigm rules.
Pre-existing artworks created before this module was installed may have
is_storable = False (the default), which permanently hides those buttons
regardless of the paradigm suppression setting.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE product_template
           SET is_storable = TRUE
         WHERE product_type = 'artwork'
           AND (is_storable IS NULL OR is_storable = FALSE)
    """)
