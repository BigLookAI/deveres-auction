# Keys are terse technical identifiers used by is_field_suppressed().
# Labels are feature-centric (describe the function suppressed, not a specific element).
# Each key may suppress multiple UI elements — see manifestation records in bridge modules.

SUPPRESSIBLE_FIELDS = [
    ('can_be_sold', 'Can be Sold'),
    ('sale_price_field', 'Sales Price'),
    ('sale_price_tab', 'Prices Tab'),
    ('cost_field', 'Cost'),
    ('sales_tab', 'Sales Tab'),
    ('can_be_purchased', 'Can be Purchased'),
    ('purchase_tab', 'Purchase Tab'),
]
