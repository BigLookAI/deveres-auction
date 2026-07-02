# Field Location Guide

## Where to Find Artwork Fields

### In the Product Form View:

1. **Open any product** (or create a new one)
2. **Go to the "General Information" tab** (first tab)
3. **Scroll down** - You should see:
   - **Category** field
   - **Artwork Type** (radio buttons: Painting, Sculpture, Print) ← **NEW**
   - **Creator/Artist** (Many2one field - can create new partners) ← **NEW**
   - **Creation Year** (Integer field) ← **NEW**

### Additional Artwork Fields:

4. **Artwork Details tab** (appears when artwork_type is selected):
   - Dimensions (Width, Height, Depth)
   - Medium
   - Edition Information

5. **Optional Information tab** (appears when artwork_type is selected):
   - Condition
   - Provenance

6. **Certificates tab** (appears when artwork_type is selected):
   - Certificate of Authenticity checkbox
   - Certificate Attachments

## If Fields Are Not Visible:

### Step 1: Refresh Browser
- Press **Ctrl+F5** (Windows/Linux) or **Cmd+Shift+R** (Mac)
- Or clear browser cache

### Step 2: Check Module is Upgraded
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db -u sor_artwork --stop-after-init
```

### Step 3: Verify in Odoo
1. Go to **Settings > Technical > User Interface > Views**
2. Search for: `product.template.form.artwork`
3. Check if the view exists and is active

### Step 4: Check Field Exists in Model
1. Go to **Settings > Technical > Database Structure > Models**
2. Search for: `product.template`
3. Check if `artwork_type`, `creator_id`, `creation_year` fields exist

### Step 5: Restart Odoo Server
Sometimes a server restart is needed after view changes.

## Expected Field Locations:

```
Product Form
├── Header (Name, Image)
├── Options (Sales/Purchase checkboxes)
└── Notebook (Tabs)
    ├── General Information Tab
    │   ├── Product Type (Goods/Service/Combo)
    │   ├── Category ← HERE
    │   ├── Artwork Type ← NEW (should be here)
    │   ├── Creator/Artist ← NEW (should be here)
    │   ├── Creation Year ← NEW (should be here)
    │   └── ... other product fields
    ├── Artwork Details Tab ← NEW (when artwork_type is set)
    ├── Optional Information Tab ← NEW (when artwork_type is set)
    ├── Certificates Tab ← NEW (when artwork_type is set)
    └── ... other tabs (Sales, Inventory, etc.)
```

## Quick Test:

1. Create a new product
2. Go to **General Information** tab
3. Look for **Category** field
4. Right below Category, you should see:
   - **Artwork Type** (radio buttons)
   - **Creator/Artist** (dropdown with "Create and Edit" button)
   - **Creation Year** (number input)

If you still don't see these fields, please check the troubleshooting steps above.

