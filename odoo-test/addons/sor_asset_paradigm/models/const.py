# Authoritative vocabulary of suppressible UI feature keys.
# Keys are terse technical identifiers used by is_element_suppressed().
# Labels are feature-centric (describe the function suppressed, not a specific element).
# Each key may suppress multiple UI elements — see manifestation records in bridge modules.

SUPPRESSIBLE_ELEMENTS = [
    ('forecast_button', 'Forecasted Stock Display'),
    ('reorder_button', 'Reorder Rules'),
    ('moves_button', 'Stock Movements'),
    ('putaway_button', 'Putaway Rules'),
    ('storage_capacity_button', 'Storage Capacities'),
    ('qty_available_field', 'Qty Available Display'),
    ('qty_column', 'Stock Quantity'),
    ('operations_group', 'Inventory Routes'),
    ('replenish_action', 'Replenish'),
    ('odoo_product_type_field', 'Odoo Product Type'),
    ('product_type_field', 'SOR Product Type'),
    ('track_inventory_field', 'Track Inventory'),
    ('inventory_tab', 'Inventory Tab'),
]
