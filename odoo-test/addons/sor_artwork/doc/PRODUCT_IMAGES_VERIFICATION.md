# Product Images Verification Guide

This document explains how to verify product images in the test database.

## Image Creation

### Artwork Images
- **Model**: `sor.art.work.image`
- **Linked to**: `product.template` (via `work_id`)
- **Default**: 3 images per artwork
- **Image Types**: Front view, Back view, Detail shot, Signature detail, Frame detail, Condition detail, Provenance document, Certificate

### Image Fields
- `work_id`: Many2one to product.template (required)
- `name`: Image description (e.g., "Front view", "Detail shot")
- `image`: Binary field containing base64-encoded PNG image
- `sequence`: Display order (lower numbers first)

## Usage

### Populate with Images
```bash
# Default: 3 images per artwork
./addons/sor_artwork/tests/populate_test_data.sh test_perf_manual

# Custom: 5 images per artwork
# Syntax: populate_test_data.sh <db> <artist> <private> <corporate> <institutions> <dealer> <buyer> <consignor> <bidder> <donor> <advisor> <artworks> <furniture> <jewelry> <collectibles> <images_per_artwork>
./addons/sor_artwork/tests/populate_test_data.sh test_perf_manual 200 150 100 50 100 100 50 50 30 30 100 50 25 25 5
```

### Verify Images
```bash
./addons/sor_artwork/tests/verify_test_data.sh test_perf_manual
```

## Verification Checklist

### In Odoo UI

1. **Go to SOR Products → All Products**
2. **Filter by Type = Artwork**
3. **Open any artwork**
4. **Go to "Images" tab**
5. **Verify**:
   - ✅ Images tab is visible (only for artworks)
   - ✅ Images are displayed in a list view
   - ✅ Images show thumbnails
   - ✅ Image descriptions are shown (Front view, Back view, etc.)
   - ✅ Images are ordered by sequence
   - ✅ Images can be reordered (drag handle)

### Image Details

1. **Click on an image** to view details
2. **Verify**:
   - ✅ Image displays correctly
   - ✅ Image description is shown
   - ✅ Sequence number is correct
   - ✅ Image can be edited/deleted

### Database Verification

The verification script checks:
- ✅ Total number of images
- ✅ Number of artworks with images
- ✅ Average images per artwork
- ✅ Min/max images per artwork
- ✅ Images by artwork subtype (Painting, Sculpture, Print)
- ✅ Image descriptions distribution
- ✅ Artworks without images (should be 0 if all artworks have images)

## Expected Results

### Default Configuration (3 images per artwork)
- **Total Images**: artwork_count × 3
- **Artworks with Images**: 100% of artworks
- **Average Images per Artwork**: 3.0
- **Image Descriptions**: Front view, Back view, Detail shot (rotating)

### Image Descriptions
1. Front view
2. Back view
3. Detail shot
4. Signature detail
5. Frame detail
6. Condition detail
7. Provenance document
8. Certificate

(Descriptions rotate if more images than descriptions)

## SQL Queries for Manual Verification

### Count Images per Artwork
```sql
SELECT 
    pt.name as artwork_name,
    pt.product_subtype,
    COUNT(img.id) as image_count
FROM product_template pt
LEFT JOIN sor_art_work_image img ON pt.id = img.work_id
WHERE pt.product_type = 'artwork'
GROUP BY pt.id, pt.name, pt.product_subtype
ORDER BY image_count DESC, pt.name;
```

### List All Images with Descriptions
```sql
SELECT 
    pt.name as artwork_name,
    img.name as image_description,
    img.sequence
FROM product_template pt
JOIN sor_art_work_image img ON pt.id = img.work_id
WHERE pt.product_type = 'artwork'
ORDER BY pt.name, img.sequence;
```

### Find Artworks without Images
```sql
SELECT 
    pt.id,
    pt.name,
    pt.product_subtype
FROM product_template pt
LEFT JOIN sor_art_work_image img ON pt.id = img.work_id
WHERE pt.product_type = 'artwork' AND img.id IS NULL;
```

### Image Statistics by Subtype
```sql
SELECT 
    pt.product_subtype,
    COUNT(DISTINCT pt.id) as artworks_count,
    COUNT(img.id) as total_images,
    ROUND(AVG(image_counts.image_count), 2) as avg_images
FROM product_template pt
JOIN sor_art_work_image img ON pt.id = img.work_id
JOIN (
    SELECT work_id, COUNT(*) as image_count
    FROM sor_art_work_image
    GROUP BY work_id
) as image_counts ON pt.id = image_counts.work_id
WHERE pt.product_type = 'artwork'
GROUP BY pt.product_subtype;
```

## Troubleshooting

### No Images Visible
1. Check if images were created:
   ```sql
   SELECT COUNT(*) FROM sor_art_work_image;
   ```
2. Check if images are linked to artworks:
   ```sql
   SELECT COUNT(DISTINCT work_id) FROM sor_art_work_image;
   ```
3. Verify image data is not NULL:
   ```sql
   SELECT COUNT(*) FROM sor_art_work_image WHERE image IS NULL;
   ```

### Images Not Displaying in UI
1. Check if artwork has `product_type = 'artwork'`
2. Verify Images tab is visible (should be invisible for non-artworks)
3. Check browser console for JavaScript errors
4. Verify image binary data is valid base64

### Performance Issues
- If creating many images, use batch commits
- Consider reducing images_per_artwork for large datasets
- Images are stored in database (not file system), so large images can slow down queries

## Related Files

- `populate_test_data.sh` - Creates artworks with images
- `verify_test_data.sh` - Verifies image counts and distribution
- `models/sor_art_work_image.py` - Image model definition
- `views/sor_art_product_views.xml` - Image view definition

---

**Last Updated**: January 14, 2026

