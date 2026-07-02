"""Backfill asset_paradigm = 'unique_object' on artwork products that existed
before this bridge module was first installed.  Runs once when upgrading from
any prior version to 19.0.1.0.1.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE product_template
           SET asset_paradigm = 'unique_object'
         WHERE product_type = 'artwork'
           AND (asset_paradigm IS NULL OR asset_paradigm != 'unique_object')
    """)
