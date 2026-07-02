# Comprehensive Creator-Artwork Relationship Test Data

This document describes the comprehensive test data created for testing US-14: Creator-Painting Relationship.

## Test Data Summary

### Contact Types Created (44 total)

#### Creators/Artists (14 total)
- **Regular Creators**: 10 creators, each with 5 artworks
- **Prolific Creator**: 1 creator with 20 artworks (performance testing)
- **Single Artwork Creator**: 1 creator with 1 artwork (edge case)
- **No Artwork Creator**: 1 creator with 0 artworks (deletion testing)
- **All Types Creator**: 1 creator with all artwork types (painting, sculpture, print)

#### Other Contact Types (30 total)
- **Private Collectors**: 5 (Customer + Private Collector subtype)
- **Corporate Collectors**: 3 (Customer + Corporate Collector subtype)
- **Institutions**: 2 (Customer + Institutions Collection subtype)
- **Dealers**: 5 (Customer + Dealer subtype)
- **Buyers**: 5 (Customer + Buyer subtype)
- **Consignors**: 3 (standalone)
- **Bidders**: 3 (standalone)
- **Donors**: 2 (standalone)
- **Advisors**: 2 (standalone)

### Artworks Created (74 total)

#### By Type
- **Paintings**: 29
- **Sculptures**: 28
- **Prints**: 17

#### By Creator
- **Prolific Creator**: 20 artworks
- **Regular Creators** (10): 5 artworks each = 50 artworks
- **All Types Creator**: 3 artworks (one of each type)
- **Single Artwork Creator**: 1 artwork
- **No Artwork Creator**: 0 artworks

### Relationships Verified
- ✅ All 74 artworks have `creator_id` populated
- ✅ All creators have `is_creator=True` and `is_artist=True`
- ✅ `artwork_ids` computed field working correctly
- ✅ `artwork_count` computed field working correctly
- ✅ 13 unique creators have artworks

## Commands

### Create Comprehensive Test Data
```bash
# Default: 10 creators, 5 artworks each
./addons/sor_artwork/tests/populate_creator_artwork_comprehensive.sh test_creator_artwork_comprehensive

# Custom: 20 creators, 10 artworks each
./addons/sor_artwork/tests/populate_creator_artwork_comprehensive.sh test_creator_artwork_comprehensive 20 10
```

### Verify All Test Data
```bash
./addons/sor_artwork/tests/verify_comprehensive_creator_artwork.sh test_creator_artwork_comprehensive
```

### View in UI
```bash
./addons/sor_artwork/tests/view_test_data.sh test_creator_artwork_comprehensive
```

## Test Cases Covered

### 1. Basic Relationship
- ✅ Creator with multiple artworks (5 artworks)
- ✅ All artwork types (painting, sculpture, print)
- ✅ All artworks linked to creators

### 2. Edge Cases
- ✅ **Prolific Creator**: 20 artworks (performance testing)
- ✅ **Single Artwork Creator**: 1 artwork (minimum case)
- ✅ **No Artwork Creator**: 0 artworks (deletion testing)
- ✅ **All Types Creator**: All artwork types (completeness testing)

### 3. Contact Type Coverage
- ✅ All 10 contact types created
- ✅ All contact subtypes created
- ✅ All standalone types created

### 4. Artwork Type Coverage
- ✅ All artwork types (painting, sculpture, print)
- ✅ All artwork fields populated (dimensions, medium, creation_year, etc.)
- ✅ Sculptures have depth and edition_info
- ✅ Prints have edition_info

### 5. Relationship Integrity
- ✅ All artworks have creators
- ✅ `artwork_ids` computed field matches direct search
- ✅ `artwork_count` computed field accurate
- ✅ Creators have correct contact types and subtypes

## UI Testing Checklist

### Creator Form View
- [ ] Open "Creator Artist 1" → Artworks tab shows 5 artworks
- [ ] Open "Prolific Creator" → Artworks tab shows 20 artworks
- [ ] Open "Single Artwork Creator" → Artworks tab shows 1 artwork
- [ ] Open "No Artwork Creator" → Artworks tab shows 0 artworks
- [ ] Open "All Types Creator" → Artworks tab shows 3 artworks (one of each type)
- [ ] Click on artwork in tab → Navigates to artwork form
- [ ] Verify artwork_count smart button (if exists)

### Artwork Form View
- [ ] Open any artwork → Creator field is populated
- [ ] Click creator name → Navigates to creator form
- [ ] Verify creator field is required (cannot save without creator)
- [ ] Verify domain filter (only shows creators/artists)

### Artwork List View
- [ ] Go to SOR Products → All Products
- [ ] Filter: Type = Artwork
- [ ] Verify Creator column shows creator name
- [ ] Click creator name → Navigates to creator form
- [ ] Group by Creator → Should show groups for each creator

### Search and Filter
- [ ] Search "Creator Artist 1" → Shows 5 artworks
- [ ] Search "Prolific Creator" → Shows 20 artworks
- [ ] Filter by Creator → Should show all creators
- [ ] Group by Creator → Should group artworks by creator

### Deletion Constraints
- [ ] Try to delete "Creator Artist 1" → Should fail (has 5 artworks)
- [ ] Try to delete "Prolific Creator" → Should fail (has 20 artworks)
- [ ] Try to delete "No Artwork Creator" → Should succeed (has 0 artworks)
- [ ] Delete artworks for "Creator Artist 1"
- [ ] Try deleting "Creator Artist 1" again → Should succeed

### Domain Filter Testing
- [ ] Create new artwork
- [ ] Click Creator field
- [ ] Verify only creators/artists shown (not Private Collectors, Dealers, etc.)
- [ ] Verify all 14 creators appear in dropdown
- [ ] Verify non-creator contacts do NOT appear

## Database Verification Queries

### Count Artworks by Creator
```sql
SELECT 
    p.name as creator_name,
    COUNT(pt.id) as artwork_count
FROM res_partner p
LEFT JOIN product_template pt ON pt.creator_id = p.id AND pt.product_type = 'artwork'
WHERE p.is_creator = true
GROUP BY p.id, p.name
ORDER BY artwork_count DESC;
```

### Count Artworks by Type
```sql
SELECT 
    product_subtype,
    COUNT(*) as count
FROM product_template
WHERE product_type = 'artwork'
GROUP BY product_subtype;
```

### Verify All Artworks Have Creators
```sql
SELECT 
    COUNT(*) as total_artworks,
    COUNT(creator_id) as with_creator,
    COUNT(*) FILTER (WHERE creator_id IS NULL) as without_creator
FROM product_template
WHERE product_type = 'artwork';
```

## Files Created

- `populate_creator_artwork_comprehensive.sh` - Creates comprehensive test data
- `verify_comprehensive_creator_artwork.sh` - Verifies all relationships
- `CREATOR_ARTWORK_RELATIONSHIP_TESTING.md` - Testing guide

---

**Last Updated**: January 15, 2026

