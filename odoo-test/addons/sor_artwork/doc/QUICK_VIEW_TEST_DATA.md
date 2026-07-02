# Quick Guide: View Test Data in UI

## Quick Start

### Option 1: Use Helper Script (Recommended)

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate

# Start Odoo with test database (creates DB if needed)
./addons/sor_artwork/tests/view_test_data.sh test_perf_manual
```

Then:
1. Open browser: `http://localhost:8069`
2. Login: Database=`test_perf_manual`, User=`admin`, Password=`admin`
3. Go to **SOR Products** → **All Products** (for artworks)
4. Go to **Contacts** → Filter by **Is Creator** = **Yes** (for creators)

---

### Option 2: Manual Start

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate

# Start Odoo server
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d test_perf_manual \
    --http-port=8069
```

---

## Create Test Data (If Needed)

If database doesn't exist or has no data:

**Option 1: Populate existing database (Recommended - Comprehensive)**
```bash
# Populate database with comprehensive test data:
# - 1000 contacts (Creators with Artist subtype)
# - 1000 artworks (Paintings, Sculptures, Prints)
# - 200 furniture items (Chairs, Tables, Desks)
# - 100 jewelry items
# - 100 other collectibles
./addons/sor_artwork/tests/populate_test_data.sh test_perf_manual

# Or with custom counts:
# Syntax: populate_test_data.sh <db> <contacts> <artworks> <furniture> <jewelry> <collectibles>
./addons/sor_artwork/tests/populate_test_data.sh test_perf_manual 1000 1000 200 100 100
```

**Option 2: Run performance tests (Creates DB + Data - Artworks only)**
```bash
# Create database with 1000+ contacts and 1000+ artworks (artworks only)
./addons/sor_artwork/tests/run_performance_tests.sh test_perf_manual
```

**Note**: Option 1 creates comprehensive data (all product types). Option 2 creates artworks only for performance testing.

---

## Where to Find Data in UI

### View All Products
- **Menu**: SOR Products → All Products
- **Expected**: ~1400+ products total
  - Artworks: ~1000 (Paintings, Sculptures, Prints)
  - Furniture: ~200 (Chairs, Tables, Desks)
  - Jewelry: ~100
  - Other Collectibles: ~100

### View by Product Type
- **Filter**: Type = Artwork → Shows paintings, sculptures, prints
- **Filter**: Type = Furniture → Shows chairs, tables, desks
- **Filter**: Type = Jewelry → Shows jewelry items
- **Filter**: Type = Other Collectible → Shows collectibles

### View by Product Sub-type
- **Filter**: Sub-type = Painting → Shows only paintings
- **Filter**: Sub-type = Sculpture → Shows only sculptures
- **Filter**: Sub-type = Print → Shows only prints
- **Filter**: Sub-type = Chair → Shows only chairs
- **Filter**: Sub-type = Table → Shows only tables
- **Filter**: Sub-type = Desk → Shows only desks

### View Contacts/Creators (1000+ records)
- **Menu**: Contacts
- **Filter**: Is Creator = Yes
- **Expected**: ~1000 creators
- **Verify**: Open any creator → Check "Contact Sub-types" field → Should show "Artist"
- **Note**: All creators have both Creator type AND Artist subtype assigned

---

## Troubleshooting

**Database doesn't exist?**
```bash
./addons/sor_artwork/tests/run_performance_tests.sh test_perf_manual
```

**Port 8069 in use?**
Change port: `--http-port=8070` then access `http://localhost:8070`

**No data?**
Run performance tests to create test data first.

---

## Stop Server

Press `Ctrl+C` in the terminal to stop the Odoo server.

