# Quick Commands for Creator-Artwork Relationship Testing

## 🚀 One-Command Setup (RECOMMENDED - Easiest!)

**For fresh machine or quick start:**

```bash
# Creates ALL contact types + ALL product types with default counts
./addons/sor_artwork/tests/scripts/populate/run_populate_all_data.sh test_large_creator_artwork
```

This single command:
- ✅ Auto-detects virtual environment
- ✅ Creates database if needed
- ✅ Installs modules if needed
- ✅ Cleans duplicates automatically
- ✅ Creates all contact types (10 types)
- ✅ Creates all product types (4 types)
- ✅ Verifies everything
- ✅ Shows summary

**Perfect for:** Fresh machine setup, reproducible test environment

---

## Alternative Commands

```bash
# Large-scale: 1000 contacts with artworks (auto-cleans DB, no duplicates)
./addons/sor_artwork/tests/scripts/populate/populate_large_creator_artwork_data.sh test_large_creator_artwork 1000 5
```

## Large-Scale Data (1000+ Records)

### Create Large Test Data (All Product Types)
```bash
# Default: 1000 contacts, 5 artworks each, 300 furniture, 200 jewelry, 200 collectibles
./addons/sor_artwork/tests/populate_large_creator_artwork_data.sh test_large_creator_artwork

# Custom: 2000 contacts, 10 artworks each, 500 furniture, 300 jewelry, 300 collectibles
./addons/sor_artwork/tests/populate_large_creator_artwork_data.sh test_large_creator_artwork 2000 10 500 300 300
```

**Parameters:**
1. Database name (default: `test_large_creator_artwork`)
2. Contact count (default: `1000`)
3. Artworks per creator (default: `5`)
4. Furniture count (default: `300`)
5. Jewelry count (default: `200`)
6. Other collectibles count (default: `200`)

**Features:**
- ✅ Automatically cleans database before inserting
- ✅ Ensures no duplicate emails
- ✅ Ensures no duplicate record names
- ✅ Creates unique emails: `creator1@test-artwork.com`, `creator2@test-artwork.com`, etc.
- ✅ Maps all artworks to creators
- ✅ Batch processing for performance
- ✅ Data integrity verification

## Comprehensive Data (All Contact Types)

### Create Comprehensive Test Data
```bash
# Default: 10 creators, 5 artworks each
./addons/sor_artwork/tests/populate_creator_artwork_comprehensive.sh test_creator_artwork_comprehensive

# Custom: 20 creators, 10 artworks each
./addons/sor_artwork/tests/populate_creator_artwork_comprehensive.sh test_creator_artwork_comprehensive 20 10
```

### Verify Test Data
```bash
./addons/sor_artwork/tests/verify_comprehensive_creator_artwork.sh test_creator_artwork_comprehensive
```

### View in UI
```bash
./addons/sor_artwork/tests/view_test_data.sh test_creator_artwork_comprehensive
```

## What Gets Created

### Large-Scale Data (All Product Types)
- **1000 Contacts**: All creators with unique emails
- **5000 Artworks**: 5 artworks per creator (Paintings, Sculptures, Prints)
- **300 Furniture**: All subtypes (Chairs, Tables, Desks)
- **200 Jewelry**: No subtypes
- **200 Other Collectibles**: No subtypes
- **No Duplicates**: Unique emails and names guaranteed
- **Auto-Clean**: Database cleaned before each run

### Comprehensive Data
- **44 Contacts**: All contact types (Creators, Collectors, Dealers, etc.)
- **74 Artworks**: All artwork types (Paintings, Sculptures, Prints)
- **Edge Cases**: Prolific creator, single artwork, no artwork, all types
- **All Relationships**: Verified and working

## Quick Verification

```bash
# Quick summary
./addons/sor_artwork/tests/verify_quick.sh test_creator_artwork_comprehensive

# Full detailed verification
./addons/sor_artwork/tests/verify_comprehensive_creator_artwork.sh test_creator_artwork_comprehensive
```

---

**Last Updated**: January 15, 2026

