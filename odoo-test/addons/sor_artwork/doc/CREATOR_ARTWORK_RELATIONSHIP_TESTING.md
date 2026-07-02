# Creator-Artwork Relationship Testing Guide

This document explains how to test the Creator-Artwork relationship (US-14) implementation.

## Test Data Created

### Creators/Artists
- **Count**: 10 creators
- **Name Pattern**: "Creator Artist 1", "Creator Artist 2", etc.
- **Contact Types**: 
  - Creator (parent type) ✅
  - Artist (subtype) ✅
- **Computed Fields**:
  - `is_creator` = True ✅
  - `is_artist` = True ✅

### Artworks
- **Total**: 50 artworks (5 per creator)
- **Distribution**:
  - Paintings: 20
  - Sculptures: 20
  - Prints: 10
- **All Linked**: Every artwork has `creator_id` field populated ✅
- **Name Pattern**: "{Artwork Type} by {Creator Name} #{Number}"
  - Example: "Oil Painting by Creator Artist 1 #1"

## Commands

### Create Test Data
```bash
# Default: 10 creators, 5 artworks each
./addons/sor_artwork/tests/populate_creator_artwork_test_data.sh test_creator_artwork

# Custom: 20 creators, 10 artworks each
./addons/sor_artwork/tests/populate_creator_artwork_test_data.sh test_creator_artwork 20 10
```

### Verify Test Data
```bash
./addons/sor_artwork/tests/verify_creator_artwork_relationship.sh test_creator_artwork
```

### View in UI
```bash
./addons/sor_artwork/tests/view_test_data.sh test_creator_artwork
```

## Testing Checklist

### 1. Creator Form View - Artworks Tab
- [ ] Go to **Contacts** → Find "Creator Artist 1"
- [ ] Open creator form view
- [ ] Check **Artworks** tab/section exists
- [ ] Verify **artwork_ids** field shows 5 artworks
- [ ] Verify artwork list shows:
  - Artwork name
  - Product subtype (Painting/Sculpture/Print)
  - Creation year
  - Medium
- [ ] Click on artwork → Should navigate to artwork form
- [ ] Check **artwork_count** smart button (if exists)
- [ ] Click smart button → Should show filtered artworks

### 2. Artwork Form View - Creator Field
- [ ] Go to **SOR Products** → **All Products**
- [ ] Filter: **Type** = **Artwork**
- [ ] Open any artwork
- [ ] Verify **Creator/Artist** field is visible
- [ ] Verify field shows creator name
- [ ] Click on creator name → Should navigate to creator form
- [ ] Verify field is required (cannot save without creator)
- [ ] Verify domain filter (only shows creators/artists)

### 3. Artwork List View - Creator Column
- [ ] Go to **SOR Products** → **All Products**
- [ ] Filter: **Type** = **Artwork**
- [ ] Verify **Creator** column is visible
- [ ] Verify column shows creator name for each artwork
- [ ] Click on creator name → Should navigate to creator form
- [ ] Verify all artworks have creator (no empty cells)

### 4. Search and Filter
- [ ] Go to **SOR Products** → **All Products**
- [ ] Filter: **Type** = **Artwork**
- [ ] In search bar, type creator name (e.g., "Creator Artist 1")
- [ ] Verify artworks by that creator are shown
- [ ] Use **Group By** → **Creator**
- [ ] Verify artworks are grouped by creator
- [ ] Verify each group shows correct creator name

### 5. Deletion Constraints
- [ ] Go to **Contacts** → Find "Creator Artist 1"
- [ ] Try to delete the creator
- [ ] Should show error: "Cannot delete creator 'Creator Artist 1' because they have 5 artwork(s)"
- [ ] Delete all artworks for that creator first
- [ ] Then try deleting creator → Should succeed

### 6. Relationship Integrity
- [ ] Open any creator → Check **artwork_ids** field
- [ ] Count artworks shown
- [ ] Go to **SOR Products** → Filter by that creator
- [ ] Count artworks in list
- [ ] Verify counts match
- [ ] Change artwork's creator
- [ ] Verify **artwork_ids** updates on both old and new creator

### 7. Domain Filter Testing
- [ ] Create new artwork
- [ ] Click on **Creator/Artist** field
- [ ] Verify only creators/artists are shown (not regular contacts)
- [ ] Verify contacts with Creator type appear
- [ ] Verify contacts with Artist subtype appear
- [ ] Verify regular contacts (non-creators) do NOT appear

### 8. Computed Fields
- [ ] Open any creator
- [ ] Check **artwork_count** field (if visible)
- [ ] Verify count matches number of artworks
- [ ] Create new artwork for that creator
- [ ] Refresh creator form
- [ ] Verify **artwork_count** increased
- [ ] Verify **artwork_ids** includes new artwork

## Expected Results

### Database Verification
```sql
-- All artworks have creators
SELECT COUNT(*) FROM product_template 
WHERE product_type = 'artwork' AND creator_id IS NULL;
-- Expected: 0

-- All creators have artworks
SELECT p.name, COUNT(pt.id) as artwork_count
FROM res_partner p
LEFT JOIN product_template pt ON pt.creator_id = p.id AND pt.product_type = 'artwork'
WHERE p.name LIKE 'Creator Artist%'
GROUP BY p.id, p.name
ORDER BY p.name;
-- Expected: All creators show 5 artworks

-- artwork_ids matches direct search
-- (Tested via verification script)
-- Expected: artwork_ids count = direct search count
```

## UI Testing Steps

### Test Creator → Artworks Navigation
1. **Contacts** → **Creator Artist 1**
2. Open form view
3. Go to **Artworks** tab
4. Verify 5 artworks listed
5. Click any artwork → Opens artwork form
6. Verify artwork shows same creator

### Test Artwork → Creator Navigation
1. **SOR Products** → **All Products**
2. Filter: **Type** = **Artwork**
3. Open "Oil Painting by Creator Artist 1 #1"
4. Click on **Creator/Artist** field
5. Should navigate to "Creator Artist 1" form
6. Verify **Artworks** tab shows this artwork

### Test Search by Creator
1. **SOR Products** → **All Products**
2. Filter: **Type** = **Artwork**
3. Search: "Creator Artist 1"
4. Should show 5 artworks
5. Group by: **Creator**
6. Should see groups for each creator

### Test Deletion Constraint
1. **Contacts** → **Creator Artist 1**
2. Try to delete
3. Should show validation error
4. Go to **Artworks** tab
5. Delete all 5 artworks
6. Try deleting creator again
7. Should succeed

## Files Created

- `populate_creator_artwork_test_data.sh` - Creates test data for relationship testing
- `verify_creator_artwork_relationship.sh` - Verifies relationship integrity

## Related Documentation

- Task: `.plan/tasks/US-14/T-implement-creator-painting-relationship.md`
- User Story: `.plan/stories/userstory-14.md`
- Test Cases: `addons/sor_artwork/tests/test_creator_artwork_relationship.py`

---

**Last Updated**: January 15, 2026

