# How to View Test Data in Odoo UI

This guide explains how to view the 1000+ contacts and 1000+ artworks created during performance testing in the Odoo web interface.

## Prerequisites

- Test database with performance test data (created by running performance tests)
- Odoo server access

## Step-by-Step Instructions

### Step 1: Identify Your Test Database

The performance tests create databases with names like:
- `test_perf_manual` (if you used `run_performance_tests.sh`)
- `test_full_verify` (if you used `run_all_tests.sh` with performance)
- `test_full_sor_artwork` (if you ran full test suite)

**Check existing databases:**
```bash
psql -l | grep test
```

### Step 2: Start Odoo Server with Test Database

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate

# Replace 'test_perf_manual' with your actual test database name
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d test_perf_manual \
    --http-port=8069
```

**Note**: The database must have been created with performance test data. If you need to create it, run:
```bash
./addons/sor_artwork/tests/run_performance_tests.sh test_perf_manual
```

### Step 3: Access Odoo Web Interface

1. Open your web browser
2. Navigate to: `http://localhost:8069`
3. Login with:
   - **Database**: Select your test database (e.g., `test_perf_manual`)
   - **Username**: `admin` (or your admin user)
   - **Password**: `admin` (or your admin password)

### Step 4: View Contacts (Creators)

1. **Navigate to Contacts**:
   - Go to **Apps** menu (or use search)
   - Search for "Contacts" or "Partners"
   - Click on **Contacts** menu item

2. **Filter for Creators**:
   - In the Contacts list view, click the **Filters** button
   - Add filter: **Is Creator** = **Yes**
   - Or search for contacts with "Artist" in the name

3. **Expected Results**:
   - You should see ~1000 contacts
   - Names like "Artist 1", "Artist 2", etc.
   - All should have Creator type assigned

### Step 5: View Artworks

1. **Navigate to SOR Products**:
   - Go to **SOR Products** menu (top-level menu)
   - Click on **All Products**
   - Or search for "SOR Products" in the Apps menu

2. **Filter for Artworks**:
   - The list should show all artworks by default
   - You can filter by:
     - **Type** = **Artwork**
     - **Sub-type** = **Painting**, **Sculpture**, or **Print**
     - **Creation Year**
     - **Creator**

3. **Expected Results**:
   - You should see ~1000 artworks
   - Names like "Artwork 1", "Artwork 2", etc.
   - Mix of paintings, sculptures, and prints
   - Each artwork linked to a creator

### Step 6: View Artwork Details

1. **Open an Artwork**:
   - Click on any artwork in the list
   - This opens the form view

2. **View Artwork Information**:
   - **General Information** tab: Type, Sub-type, Creator, Creation Year
   - **Product Details** tab: Dimensions, Medium, Edition Info
   - **Optional Information** tab: Condition, Provenance
   - **Certificates** tab: Certificate of Authenticity
   - **Images** tab: Artwork images (if created)

### Step 7: Search and Filter

**Search Contacts**:
- Use the search bar in Contacts
- Search by name: "Artist"
- Filter by contact type: Creator

**Search Artworks**:
- Use the search bar in SOR Products
- Search by name: "Artwork"
- Filter by:
  - Type: Artwork
  - Sub-type: Painting, Sculpture, Print
  - Creator: Select a specific creator
  - Creation Year: Filter by year range
  - Medium: Filter by medium type

## Quick Access Script

Use the helper script to quickly start Odoo with your test database:

```bash
# Make script executable (first time only)
chmod +x addons/sor_artwork/tests/view_test_data.sh

# Run the script
./addons/sor_artwork/tests/view_test_data.sh test_perf_manual
```

## Troubleshooting

### Issue: Database doesn't exist
**Solution**: Create the test database first:
```bash
./addons/sor_artwork/tests/run_performance_tests.sh test_perf_manual
```

### Issue: No data in database
**Solution**: The performance tests create the data. Make sure you ran:
```bash
./addons/sor_artwork/tests/run_performance_tests.sh test_perf_manual
```
Or:
```bash
./addons/sor_artwork/tests/run_all_tests.sh test_perf_manual yes
```

### Issue: Can't see SOR Products menu
**Solution**: Make sure the module is installed:
```bash
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d test_perf_manual \
    -u sor_artwork \
    --stop-after-init
```

### Issue: Port 8069 already in use
**Solution**: Use a different port:
```bash
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d test_perf_manual \
    --http-port=8070
```
Then access: `http://localhost:8070`

## Expected Data Counts

After running performance tests, you should see:
- **Contacts (Creators)**: ~1000 records
- **Artworks**: ~1000 records
  - Paintings: ~334
  - Sculptures: ~333
  - Prints: ~333
- **Images**: ~300 (3 per artwork, limited to 100 artworks)

## Viewing Specific Data

### View All Artworks by a Specific Creator

1. Go to **Contacts**
2. Find and open a creator (e.g., "Artist 1")
3. Check if there's an **Artworks** tab or related field
4. Or go to **SOR Products** and filter by that creator

### View Artworks by Type

1. Go to **SOR Products**
2. Use the filter: **Sub-type** = **Painting** (or Sculpture, Print)
3. You should see all artworks of that type

### View Artworks by Creation Year

1. Go to **SOR Products**
2. Use the filter: **Creation Year** = **2020** (or any year 2000-2024)
3. You should see artworks created in that year

## Notes

- Test data is created during performance test execution
- The data persists in the database until you drop it
- You can create multiple test databases with different names
- Each test run creates fresh data (drops existing test data first)

## Cleanup

When done viewing test data, you can:
1. Stop the Odoo server (Ctrl+C)
2. Keep the database for future viewing
3. Or drop it to free space:
   ```bash
   dropdb test_perf_manual
   ```

