# Data Verification Checklist

Use this checklist to verify all test data is created correctly in the UI.

## Contacts Verification

### ✅ Creator Contacts with Artist Subtype
1. Go to **Contacts** menu
2. Filter by **Is Creator** = **Yes**
3. **Expected**: ~1000 contacts named "Artist 1", "Artist 2", etc.
4. **Verify**: Open any contact → Check **Contact Types** field
   - Should show: **Creator** (parent type)
5. **Verify**: Check **Contact Sub-types** field
   - Should show: **Artist** (subtype of Creator)
6. **Verify**: Check computed fields
   - `is_creator` = True ✅
   - `is_artist` = True ✅

## Products Verification

### ✅ Artworks (Type: Artwork)
1. Go to **SOR Products** → **All Products**
2. Filter by **Type** = **Artwork**
3. **Expected**: ~1000 artworks
4. **Verify Sub-types**:
   - Filter by **Sub-type** = **Painting** → Should see ~334 paintings
   - Filter by **Sub-type** = **Sculpture** → Should see ~333 sculptures
   - Filter by **Sub-type** = **Print** → Should see ~333 prints
5. **Verify Fields**:
   - Open a **Painting** → Should have: dimensions (width, height), medium, creation_year, creator_id
   - Open a **Sculpture** → Should have: dimensions (width, height, **depth**), medium, creation_year, **edition_info**, creator_id
   - Open a **Print** → Should have: dimensions (width, height), medium, creation_year, **edition_info**, creator_id
6. **Verify Creator Link**:
   - Open any artwork → Check **Creator/Artist** field
   - Should link to a contact with Creator type and Artist subtype

### ✅ Furniture (Type: Furniture)
1. Filter by **Type** = **Furniture**
2. **Expected**: ~200 furniture items
3. **Verify Sub-types**:
   - Filter by **Sub-type** = **Chair** → Should see ~67 chairs
   - Filter by **Sub-type** = **Table** → Should see ~67 tables
   - Filter by **Sub-type** = **Desk** → Should see ~66 desks
4. **Verify Fields**:
   - Open any furniture → Should have: dimensions (width, height), medium
   - Should NOT have: creator_id, creation_year, edition_info, dimensions_depth
5. **Verify Names**:
   - Chairs: "Antique Chair", "Modern Chair", "Designer Chair", "Vintage Chair"
   - Tables: "Dining Table", "Coffee Table", "Side Table", "Console Table"
   - Desks: "Writing Desk", "Executive Desk", "Vintage Desk", "Modern Desk"

### ✅ Jewelry (Type: Jewelry)
1. Filter by **Type** = **Jewelry**
2. **Expected**: ~100 jewelry items
3. **Verify**:
   - Sub-type field should be empty (no subtypes for jewelry yet)
   - Should have: medium field
   - Names: "Vintage Necklace", "Antique Ring", "Art Deco Bracelet", etc.

### ✅ Other Collectibles (Type: Other Collectible)
1. Filter by **Type** = **Other Collectible**
2. **Expected**: ~100 collectibles
3. **Verify**:
   - Sub-type field should be empty (no subtypes for other_collectible yet)
   - Should have: medium field
   - Names: "Vintage Watch", "Antique Vase", "Rare Book", etc.

## Data Counts Verification

### Expected Counts (Default: 1000 contacts, 1000 artworks, 200 furniture, 100 jewelry, 100 collectibles)

| Product Type | Sub-type | Expected Count | Verify in UI |
|--------------|----------|----------------|--------------|
| Artwork | Painting | ~334 | Filter: Type=Artwork, Sub-type=Painting |
| Artwork | Sculpture | ~333 | Filter: Type=Artwork, Sub-type=Sculpture |
| Artwork | Print | ~333 | Filter: Type=Artwork, Sub-type=Print |
| Furniture | Chair | ~67 | Filter: Type=Furniture, Sub-type=Chair |
| Furniture | Table | ~67 | Filter: Type=Furniture, Sub-type=Table |
| Furniture | Desk | ~66 | Filter: Type=Furniture, Sub-type=Desk |
| Jewelry | (none) | ~100 | Filter: Type=Jewelry |
| Other Collectible | (none) | ~100 | Filter: Type=Other Collectible |
| **TOTAL** | | **~1400** | SOR Products → All Products |

## Field Validation

### Artwork Fields
- ✅ `product_type` = 'artwork'
- ✅ `product_subtype` = 'painting' | 'sculpture' | 'print'
- ✅ `dimensions_width` = positive number
- ✅ `dimensions_height` = positive number
- ✅ `dimensions_depth` = positive number (sculptures only)
- ✅ `medium` = string value
- ✅ `creation_year` = 2000-2024
- ✅ `creator_id` = links to contact with Creator type
- ✅ `edition_info` = present (sculptures and prints only)

### Furniture Fields
- ✅ `product_type` = 'furniture'
- ✅ `product_subtype` = 'chair' | 'table' | 'desk'
- ✅ `dimensions_width` = positive number
- ✅ `dimensions_height` = positive number
- ✅ `medium` = string value (wood type, material)
- ✅ `creator_id` = False (furniture doesn't have creators)
- ✅ `creation_year` = False (furniture doesn't have creation year)
- ✅ `edition_info` = False (furniture doesn't have edition info)

### Contact Fields
- ✅ `contact_types` = Contains Creator type
- ✅ `contact_subtypes` = Contains Artist subtype
- ✅ `is_creator` = True (computed)
- ✅ `is_artist` = True (computed)

## Search and Filter Testing

### Test Search Functionality
1. **Search by Name**: Search "Painting" → Should find paintings
2. **Search by Medium**: Search "Bronze" → Should find sculptures with bronze medium
3. **Search by Creator**: Search creator name → Should find their artworks

### Test Filter Combinations
1. **Type + Sub-type**: Type=Artwork + Sub-type=Painting → Only paintings
2. **Type + Year**: Type=Artwork + Creation Year=2020 → Artworks from 2020
3. **Type + Creator**: Type=Artwork + Creator=[specific creator] → Creator's artworks

### Test Grouping
1. **Group by Type**: Should show counts for Artwork, Furniture, Jewelry, Other Collectible
2. **Group by Sub-type**: Should show counts for Painting, Sculpture, Print, Chair, Table, Desk
3. **Group by Creator**: Should show artworks grouped by creator

## UI Navigation Testing

### Menu Items
- ✅ **SOR Products** menu exists (top-level)
- ✅ **All Products** submenu exists
- ✅ Menu shows all product types

### Views
- ✅ **List View**: Shows all products with relevant columns
- ✅ **Form View**: Shows all fields organized in tabs
- ✅ **Search View**: Has filters for Type, Sub-type, Creator, etc.

## Performance Verification

### List View Performance
- ✅ List view loads quickly (< 2 seconds for 1000+ records)
- ✅ Pagination works correctly
- ✅ Sorting works correctly

### Search Performance
- ✅ Search is responsive (< 1 second)
- ✅ Filters apply quickly
- ✅ Grouping works efficiently

## Data Relationships

### Creator-Artwork Relationship
1. Open any artwork
2. Click on **Creator/Artist** field
3. Should navigate to contact with:
   - Creator type assigned ✅
   - Artist subtype assigned ✅
   - `is_creator` = True ✅
   - `is_artist` = True ✅

### Reverse Relationship (if implemented)
1. Open any creator contact
2. Check if there's an **Artworks** field or related view
3. Should show all artworks by that creator

## Summary

After running the populate script, verify:
- ✅ All product types created (Artwork, Furniture, Jewelry, Other Collectible)
- ✅ All product sub-types created (Painting, Sculpture, Print, Chair, Table, Desk)
- ✅ All contacts have Creator type AND Artist subtype
- ✅ All artworks linked to creators
- ✅ All fields populated correctly
- ✅ Search and filters work
- ✅ Views load correctly
- ✅ Performance is acceptable

---

**Last Updated**: January 14, 2026
**Script**: `./addons/sor_artwork/tests/populate_test_data.sh`

