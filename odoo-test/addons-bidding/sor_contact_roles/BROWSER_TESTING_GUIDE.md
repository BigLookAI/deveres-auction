# Browser Testing Guide - SOR Contact Roles

## Quick Fix Applied ✅

Fixed the JavaScript error in the Kanban view that was causing:
```
TypeError: undefined is not an object (evaluating 'error.stack.split')
```

**What was fixed:**
- Removed unsafe string manipulation in Kanban template
- Added proper `title` attributes to Font Awesome icons
- Used Odoo field widgets instead of raw JavaScript string operations

## Steps to Test in Browser

### 1. Start Odoo Server

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db
```

**Note:** Use your actual database name (not `test_db` if you're using a different one)

### 2. Access Odoo in Browser

Open your browser and go to:
```
http://localhost:8069
```

### 3. Login and Navigate to Contacts

1. **Login** with your Odoo credentials
2. Go to **Contacts** app (or use the Apps menu)
3. Navigate to **Contacts** → **Contacts by Type**

### 4. Test Contact Type Assignment

1. **Create or Edit a Contact:**
   - Click **Create** or open an existing contact
   - You should see:
     - **Contact Types** field (with tags widget)
     - **Sub-Types** field (appears when Creator or Customer is selected)

2. **Test Creator Type:**
   - Select **Creator** in Contact Types
   - **Sub-Types** field should appear
   - Select **Artist** sub-type
   - Go to **Creator Information** tab (should be visible)
   - Fill in: Biography, Birth Date, Nationality, Website
   - Add Social Media profiles

3. **Test Customer Type:**
   - Select **Customer** in Contact Types
   - **Sub-Types** field should appear
   - Select **Private Collector** or other customer sub-types
   - Go to **Customer Information** tab (should be visible)
   - Fill in: Collection Focus, Preferred Artists

4. **Test Multiple Types:**
   - Select both **Creator** and **Advisor**
   - Both tabs should be visible
   - Verify computed fields work (is_creator, is_advisor, etc.)

### 5. Test Kanban View

1. Navigate to **Contacts** → **Contacts by Type** → **By Type (Kanban)**
2. The Kanban view should load without JavaScript errors
3. Cards should display:
   - Contact name
   - Contact types as tags
   - Email and phone (if available)
   - Biography/Collection focus (if available)

### 6. Test List Views

Navigate to:
- **Contacts** → **Contacts by Type** → **Creators**
- **Contacts** → **Contacts by Type** → **Customers**
- **Contacts** → **Contacts by Type** → **Advisors**

Each should show filtered lists of contacts.

### 7. Test Search and Filters

1. Go to **Contacts** list view
2. In the search bar, you should see:
   - **Contact Type** filter
   - **Sub-Type** filter
   - Quick filters: Creators, Artists, Customers, etc.
3. Test filtering by contact type

## Troubleshooting

### Issue: Module not visible in menu

**Solution:**
```bash
# Upgrade the module
python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
  -u sor_contact_roles --stop-after-init
```

### Issue: JavaScript errors in browser console

**Solution:**
1. Clear browser cache (Ctrl+Shift+Delete or Cmd+Shift+Delete)
2. Restart Odoo server
3. Upgrade module again

### Issue: Fields not showing

**Check:**
1. Is the contact type assigned? (Contact Types field)
2. Are you looking at the right tab? (Creator Information / Customer Information)
3. Check browser console for errors

### Issue: "Contact Types" field not visible

**Solution:**
- Make sure module is installed and upgraded
- Check user permissions
- Try creating a new contact (not editing existing)

## Expected Behavior

### Contact Form
- ✅ Contact Types field appears after Categories field
- ✅ Sub-Types field appears when Creator or Customer is selected
- ✅ Creator Information tab appears when Creator type is assigned
- ✅ Customer Information tab appears when Customer type is assigned
- ✅ Social Media section appears in Creator Information tab

### Kanban View
- ✅ Loads without JavaScript errors
- ✅ Shows contact cards grouped by contact type
- ✅ Displays contact information correctly
- ✅ No console errors

### List Views
- ✅ Filtered lists show correct contacts
- ✅ Search and filters work
- ✅ Contact type tags display correctly

## Browser Console Check

Open browser Developer Tools (F12) and check:

1. **Console Tab:**
   - Should have NO red errors
   - Warnings are usually OK

2. **Network Tab:**
   - All requests should return 200 OK
   - No 404 or 500 errors

3. **Application Tab (Chrome):**
   - Check if assets are loaded correctly

## Quick Test Checklist

- [ ] Module installed and upgraded
- [ ] Can create/edit contacts
- [ ] Contact Types field visible
- [ ] Sub-Types field appears when needed
- [ ] Creator Information tab visible for creators
- [ ] Customer Information tab visible for customers
- [ ] Kanban view loads without errors
- [ ] List views show filtered contacts
- [ ] Search and filters work
- [ ] No JavaScript errors in console

## If Still Having Issues

1. **Check Odoo Logs:**
   ```bash
   # Look for errors in terminal where Odoo is running
   ```

2. **Check Browser Console:**
   - Open Developer Tools (F12)
   - Check Console tab for errors
   - Check Network tab for failed requests

3. **Verify Module Installation:**
   ```bash
   python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
     -i sor_contact_roles --stop-after-init
   ```

4. **Try Fresh Database:**
   ```bash
   # Create new test database
   createdb test_fresh
   python3 odoo-bin --addons-path=addons,odoo/addons -d test_fresh \
     -i base,sor_contact_roles --stop-after-init
   ```

## Contact Type Codes Reference

- **Parent Types:** creator, customer, advisor, consignor, bidder, donor
- **Creator Sub-Types:** artist
- **Customer Sub-Types:** private_collector, corporate_collector, institutions_collection, dealer, buyer

