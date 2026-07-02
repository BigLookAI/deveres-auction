#!/bin/bash
# Quick verification script for test data

DB_NAME=${1:-test_perf_manual}

echo "============================================================"
echo "Quick Verification: $DB_NAME"
echo "============================================================"
echo ""

# Contact counts
echo "=== Contact Counts ==="
psql "$DB_NAME" -c "
SELECT 
    CASE 
        WHEN name LIKE 'Artist%' THEN 'Artists'
        WHEN name LIKE 'Private Collector%' THEN 'Private Collectors'
        WHEN name LIKE 'Corporate Collector%' THEN 'Corporate Collectors'
        WHEN name LIKE 'Institutions Collection%' THEN 'Institutions'
        WHEN name LIKE 'Dealer%' THEN 'Dealers'
        WHEN name LIKE 'Buyer%' THEN 'Buyers'
        WHEN name LIKE 'Consignor%' THEN 'Consignors'
        WHEN name LIKE 'Bidder%' THEN 'Bidders'
        WHEN name LIKE 'Donor%' THEN 'Donors'
        WHEN name LIKE 'Advisor%' THEN 'Advisors'
    END as contact_type,
    COUNT(*) as count
FROM res_partner
WHERE name LIKE 'Artist%' 
   OR name LIKE 'Private Collector%'
   OR name LIKE 'Corporate Collector%'
   OR name LIKE 'Institutions Collection%'
   OR name LIKE 'Dealer%'
   OR name LIKE 'Buyer%'
   OR name LIKE 'Consignor%'
   OR name LIKE 'Bidder%'
   OR name LIKE 'Donor%'
   OR name LIKE 'Advisor%'
GROUP BY contact_type
ORDER BY contact_type;
" 2>/dev/null

# Product counts
echo ""
echo "=== Product Counts ==="
psql "$DB_NAME" -c "
SELECT 
    product_type,
    COALESCE(product_subtype::text, '(none)') as product_subtype,
    COUNT(*) as count
FROM product_template 
WHERE product_type IS NOT NULL 
GROUP BY product_type, product_subtype 
ORDER BY product_type, product_subtype;
" 2>/dev/null

# Images
echo ""
echo "=== Artwork Images ==="
psql "$DB_NAME" -c "
SELECT 
    COUNT(*) as total_images,
    COUNT(DISTINCT work_id) as artworks_with_images,
    ROUND(AVG(image_count), 2) as avg_images_per_artwork
FROM (
    SELECT work_id, COUNT(*) as image_count
    FROM sor_art_work_image
    GROUP BY work_id
) as image_counts;
" 2>/dev/null

# Artworks with creators
echo ""
echo "=== Artworks with Creators ==="
psql "$DB_NAME" -c "
SELECT 
    COUNT(*) as total_artworks,
    COUNT(creator_id) as artworks_with_creator
FROM product_template 
WHERE product_type = 'artwork';
" 2>/dev/null

echo ""
echo "============================================================"
echo "✅ Quick verification complete"
echo "============================================================"

