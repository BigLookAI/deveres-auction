# Quick Start Guide - Test Data Population

## One-Command Setup

To populate all test data (all contact types + all product types) in one command:

```bash
./addons/sor_artwork/tests/scripts/populate/run_populate_all_data.sh test_large_creator_artwork
```

This single command will:
- ✅ Clean duplicates (if any)
- ✅ Clean all existing test data
- ✅ Create all contact types (Creators, Collectors, Dealers, etc.)
- ✅ Create all product types (Artworks, Furniture, Jewelry, Collectibles)
- ✅ Map artworks to creators
- ✅ Verify all data integrity
- ✅ Show comprehensive summary

## What Gets Created

### Contact Types (Total: ~2000 contacts)
- **Creators/Artists**: 1000 (mapped to artworks)
- **Private Collectors**: 200
- **Corporate Collectors**: 100
- **Institutions**: 50
- **Dealers**: 150
- **Buyers**: 150
- **Consignors**: 100
- **Bidders**: 100
- **Donors**: 50
- **Advisors**: 50

### Product Types (Total: ~5700 products)
- **Artworks**: ~5000 (5 per creator)
  - Paintings
  - Sculptures
  - Prints
- **Furniture**: 300
  - Chairs
  - Tables
  - Desks
- **Jewelry**: 200
- **Other Collectibles**: 200

## Custom Counts

To customize the counts, pass parameters:

```bash
./addons/sor_artwork/tests/run_populate_all_data.sh test_large_creator_artwork \
  2000 10 500 200 100 100 300 300 200 200 100 100 500 300 300
```

**Parameters (in order):**
1. Database name
2. Creator count
3. Artworks per creator
4. Private Collectors
5. Corporate Collectors
6. Institutions
7. Dealers
8. Buyers
9. Consignors
10. Bidders
11. Donors
12. Advisors
13. Furniture count
14. Jewelry count
15. Collectibles count

## Prerequisites

1. **Virtual Environment**: The script will auto-detect and activate `env312` or `env`
2. **Database**: Will be created automatically if it doesn't exist
3. **Modules**: Will be installed automatically (`base`, `product`, `sor_contact_roles`, `sor_artwork`)

## Features

- ✅ **Auto-clean**: Removes duplicates and existing test data before creating new
- ✅ **No duplicates**: Ensures unique emails and names
- ✅ **Full verification**: 7-point data integrity check
- ✅ **All mappings**: Artworks properly mapped to creators
- ✅ **All types**: All contact types and product types created

## After Running

### View in UI
```bash
./addons/sor_artwork/tests/scripts/utils/view_test_data.sh test_large_creator_artwork
```

### Verify Data
```bash
./addons/sor_artwork/tests/scripts/verify/verify_quick.sh test_large_creator_artwork
```

### Clean Duplicates (if needed)
```bash
./addons/sor_artwork/tests/scripts/utils/clean_duplicates.sh test_large_creator_artwork
```

## Troubleshooting

### If you get "Module not found" errors:
```bash
# Make sure modules are installed
python3 odoo-bin --addons-path=addons,odoo/addons -d test_large_creator_artwork \
  -i base,product,sor_contact_roles,sor_artwork --stop-after-init
```

### If you get duplicate errors:
```bash
# Clean duplicates first
./addons/sor_artwork/tests/scripts/utils/clean_duplicates.sh test_large_creator_artwork yes
```

### If database doesn't exist:
The script will create it automatically. Just run:
```bash
./addons/sor_artwork/tests/scripts/populate/run_populate_all_data.sh test_large_creator_artwork
```

---

**Last Updated**: January 16, 2026

