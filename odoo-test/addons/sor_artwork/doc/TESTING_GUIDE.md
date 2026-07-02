# SOR Artwork Management - Testing Guide

## Prerequisites
- Module `sor_artwork` is installed
- You have access to the Odoo database
- You're logged in as a user with appropriate permissions

## Testing Steps

### 1. Access the Art Products Menu
**Expected Result:** Menu should be visible and accessible

**Steps:**
1. Login to Odoo
2. Navigate to: **Sales > Products > Artwork > Art Products**
3. You should see an empty list (or existing art products if any)

**Verification:**
- ✅ Menu "Art Products" is visible
- ✅ List view loads without errors
- ✅ You can see the action button to create new records

---

### 2. Test Creating a Painting (Type: Painting - 1.1)

**Expected Result:** Painting should be created with only width/height dimensions (no depth, no edition_info)

**Steps:**
1. Click **Create** button
2. Fill in the form:
   - **Name:** "Sunset Over Mountains"
   - **Artwork Type:** Select "Painting"
   - **Creator/Artist:** Click the field, then click "Create and Edit" or "Create" to add a new partner, or select an existing partner (e.g., "John Artist")
   - **Creation Year:** 2020
   - **Width:** 100.00
   - **Height:** 80.00
   - **Medium:** "Oil on canvas"
   - **Sales Price:** 5000.00 (from General Information tab)
3. **DO NOT** fill in:
   - Depth (should not be visible)
   - Edition Information (should not be visible)
4. Click **Save**

**Verification:**
- ✅ Record is saved successfully
- ✅ "Depth" field is NOT visible in the form
- ✅ "Edition Information" field is NOT visible in the form
- ✅ Width and Height are required and saved
- ✅ All fields are saved correctly

---

### 3. Test Creating a Sculpture (Type: Sculpture - 1.2)

**Expected Result:** Sculpture should require depth and show edition_info field

**Steps:**
1. Click **Create** button
2. Fill in the form:
   - **Name:** "Bronze Statue"
   - **Artwork Type:** Select "Sculpture"
   - **Creator/Artist:** Select a partner
   - **Creation Year:** 2019
   - **Width:** 50.00
   - **Height:** 120.00
   - **Depth:** 40.00 (should now be visible)
   - **Medium:** "Bronze"
   - **Edition Information:** "1/10" (should now be visible)
   - **Condition:** "Excellent"
   - **Provenance:** "Private collection, Paris"
   - **Certificate of Authenticity:** Check the box
3. Click **Save**

**Verification:**
- ✅ Record is saved successfully
- ✅ "Depth" field IS visible and required
- ✅ "Edition Information" field IS visible
- ✅ All fields are saved correctly
- ✅ Certificate of Authenticity checkbox is saved

**Test Validation - Try to save without depth:**
1. Create a new sculpture
2. Fill all fields EXCEPT "Depth"
3. Try to save
4. **Expected:** Error message "Depth is required for sculptures"

---

### 4. Test Creating a Print (Type: Print - 1.3)

**Expected Result:** Print should show depth (optional) and edition_info

**Steps:**
1. Click **Create** button
2. Fill in the form:
   - **Name:** "Limited Edition Print"
   - **Artwork Type:** Select "Print"
   - **Creator/Artist:** Select a partner
   - **Creation Year:** 2021
   - **Width:** 60.00
   - **Height:** 90.00
   - **Depth:** 2.00 (optional, for framed prints)
   - **Medium:** "Lithograph"
   - **Edition Information:** "15/50"
   - **Provenance:** "Gallery acquisition"
3. Click **Save**

**Verification:**
- ✅ Record is saved successfully
- ✅ "Depth" field IS visible (but optional, not required)
- ✅ "Edition Information" field IS visible
- ✅ All fields are saved correctly

---

### 5. Test Field Visibility Changes (Dynamic Visibility)

**Expected Result:** Fields should show/hide when artwork type changes

**Steps:**
1. Create a new artwork record
2. Select **Artwork Type:** "Painting"
3. **Verify:** Depth and Edition Information are NOT visible
4. Change **Artwork Type** to "Sculpture"
5. **Verify:** Depth and Edition Information ARE now visible
6. Change **Artwork Type** to "Print"
7. **Verify:** Depth and Edition Information remain visible
8. Change back to "Painting"
9. **Verify:** Depth and Edition Information disappear again

**Verification:**
- ✅ Field visibility changes immediately when type changes
- ✅ No page refresh needed
- ✅ Fields appear/disappear correctly

---

### 6. Test Validation Constraints

#### 6.1 Test Required Fields
**Steps:**
1. Create new artwork
2. Try to save without:
   - Name (should fail - product.template requirement)
   - Width (should fail - our requirement)
   - Height (should fail - our requirement)
   - Artwork Type (should fail if we make it required)

**Verification:**
- ✅ Appropriate error messages appear
- ✅ Record cannot be saved without required fields

#### 6.2 Test Positive Dimension Values
**Steps:**
1. Create new artwork
2. Set **Width:** -10 (negative value)
3. Try to save
4. **Expected:** Error "Width must be a positive value"

5. Set **Width:** 0
6. Try to save
7. **Expected:** Error "Width must be a positive value"

8. Set **Height:** -5
9. Try to save
10. **Expected:** Error "Height must be a positive value"

**Verification:**
- ✅ Negative values are rejected
- ✅ Zero values are rejected
- ✅ Only positive values are accepted

#### 6.3 Test Depth Validation for Sculptures
**Steps:**
1. Create new sculpture
2. Leave **Depth** empty
3. Try to save
4. **Expected:** Error "Depth is required for sculptures"

5. Set **Depth:** -5
6. Try to save
7. **Expected:** Error "Depth must be a positive value"

**Verification:**
- ✅ Depth is required for sculptures
- ✅ Depth must be positive

#### 6.4 Test Creation Year Range
**Steps:**
1. Create new artwork
2. Set **Creation Year:** 500
3. Try to save
4. **Expected:** Error "Creation year must be between 1000 and 2100"

5. Set **Creation Year:** 2500
6. Try to save
7. **Expected:** Error "Creation year must be between 1000 and 2100"

8. Set **Creation Year:** 1500
9. Try to save
10. **Expected:** Should save successfully

**Verification:**
- ✅ Years outside 1000-2100 range are rejected
- ✅ Years within range are accepted

---

### 7. Test Certificate Attachments

**Steps:**
1. Create or edit an artwork
2. Check **Certificate of Authenticity** checkbox
3. In the **Certificates** tab, click **Add a line** in Certificate Attachments
4. Upload a file (PDF, image, etc.)
5. Click **Save**

**Verification:**
- ✅ Certificate checkbox is saved
- ✅ Attachment is uploaded and linked
- ✅ Attachment appears in the list
- ✅ Attachment can be downloaded/viewed

---

### 8. Test List View

**Steps:**
1. Go to Art Products list view
2. Check the columns displayed

**Verification:**
- ✅ Columns show: Name, Artwork Type, Creation Year, Width, Height, Medium, Creator
- ✅ Artwork Type shows with color badges (blue for painting, green for sculpture, yellow for print)
- ✅ Optional columns can be shown/hidden
- ✅ Records are sortable by clicking column headers

---

### 9. Test Search and Filters

#### 9.1 Test Search Fields
**Steps:**
1. In the search bar, type an artwork name
2. **Verify:** Results are filtered

3. Search by creator name
4. **Verify:** Results show artworks by that creator

5. Search by medium
6. **Verify:** Results show artworks with that medium

**Verification:**
- ✅ Search works for name, creator, medium, creation year

#### 9.2 Test Filters
**Steps:**
1. Click **Filters** dropdown
2. Select **Paintings** filter
3. **Verify:** Only paintings are shown

4. Select **Sculptures** filter
5. **Verify:** Only sculptures are shown

6. Select **Prints** filter
7. **Verify:** Only prints are shown

8. Select **With Certificate** filter
9. **Verify:** Only artworks with certificates are shown

**Verification:**
- ✅ All filters work correctly
- ✅ Filters can be combined
- ✅ Filters can be cleared

#### 9.3 Test Group By
**Steps:**
1. Click **Group By** dropdown
2. Select **Artwork Type**
3. **Verify:** Records are grouped by type (Painting, Sculpture, Print)

4. Select **Medium**
5. **Verify:** Records are grouped by medium

6. Select **Creator**
7. **Verify:** Records are grouped by creator

**Verification:**
- ✅ Group by options work correctly
- ✅ Records are properly grouped

---

### 10. Test Integration with Product Template

**Steps:**
1. Create an artwork
2. Go to **General Information** tab
3. Fill in:
   - **Description:** "Beautiful artwork description"
   - **Product Category:** Select a category
   - **Sales Price:** 10000.00
   - **Cost:** 5000.00
4. Save

**Verification:**
- ✅ All product.template fields are accessible
- ✅ Product fields are saved correctly
- ✅ Artwork can be used in sales orders (if sale module installed)
- ✅ Regular products (without artwork_type) are not affected

---

### 11. Test Domain Filter

**Steps:**
1. Go to regular Products menu (Sales > Products > Products)
2. **Verify:** Art products (with artwork_type) are NOT shown in regular product list

3. Go to Art Products menu
4. **Verify:** Only art products (with artwork_type set) are shown

**Verification:**
- ✅ Domain filter `[('artwork_type', '!=', False)]` works correctly
- ✅ Art products are separated from regular products

---

### 12. Test Optional Fields

**Steps:**
1. Create artwork with:
   - **Condition:** "Good condition"
   - **Provenance:** "Acquired from gallery in 2020"
2. Save

3. Create another artwork without condition and provenance
4. Save

**Verification:**
- ✅ Optional fields can be left empty
- ✅ Optional fields are saved when filled
- ✅ Both records save successfully

---

## Test Summary Checklist

### Core Functionality
- [ ] Can create Painting (1.1) with correct fields
- [ ] Can create Sculpture (1.2) with depth and edition_info
- [ ] Can create Print (1.3) with optional depth and edition_info
- [ ] Field visibility changes dynamically based on type

### Validation
- [ ] Required fields are enforced (width, height)
- [ ] Depth is required for sculptures
- [ ] Dimensions must be positive
- [ ] Creation year must be between 1000-2100
- [ ] Error messages are clear and helpful

### Views
- [ ] Form view shows all sections correctly
- [ ] List view displays relevant columns
- [ ] Search view has all filters and group-by options
- [ ] Dynamic field visibility works in form view

### Integration
- [ ] Product.template fields are accessible
- [ ] Regular products are not affected
- [ ] Domain filter separates art products from regular products
- [ ] Certificate attachments work correctly

### Menu and Navigation
- [ ] Menu is visible at Sales > Products > Artwork > Art Products
- [ ] Action opens correct view with domain filter
- [ ] Can create, edit, and delete art products

---

## Expected Test Results

After completing all tests, you should have:
- ✅ 3+ artwork records (at least one of each type)
- ✅ Verified all field visibility rules
- ✅ Verified all validation constraints
- ✅ Verified search, filters, and group-by functionality
- ✅ Verified certificate attachments
- ✅ Verified integration with product.template

---

## Troubleshooting

### If fields don't show/hide:
- Clear browser cache
- Restart Odoo server
- Check browser console for JavaScript errors

### If validation doesn't work:
- Check Odoo logs for Python errors
- Verify model constraints are properly defined
- Test in Odoo shell if needed

### If menu doesn't appear:
- Verify sale module is installed
- Check user permissions
- Upgrade the module: `-u sor_artwork`

---

## Quick Test Commands (Optional)

If you want to test via Odoo shell:

```bash
python3 odoo-bin shell -d test_db
```

Then in the shell:
```python
# Check model exists
env['product.template']._fields.get('artwork_type')

# Create a test artwork
artwork = env['product.template'].create({
    'name': 'Test Painting',
    'artwork_type': 'painting',
    'dimensions_width': 100.0,
    'dimensions_height': 80.0,
    'medium': 'Oil',
    'type': 'consu',  # Product type from product.template
})

# Verify it was created
artwork.artwork_type  # Should return 'painting'

# Test validation
try:
    artwork.write({'dimensions_width': -10})
except Exception as e:
    print(f"Validation works: {e}")
```

