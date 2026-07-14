# Simple Test Runner Guide

## Quick Fix for "ModuleNotFoundError: No module named 'babel'"

The error occurs because:
1. Virtual environment is not activated
2. Dependencies are not installed

## Solution 1: Use the Test Script (Recommended)

```bash
cd /Users/deepkharadi/Documents/BL
./addons/sor_contact_roles/tests/run_tests.sh
```

Or specify a database:
```bash
./addons/sor_contact_roles/tests/run_tests.sh my_test_db
```

## Solution 2: Manual Steps

### Step 1: Activate Virtual Environment
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Create Test Database (if needed)
```bash
createdb test_db
```

### Step 4: Install Module
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  -i base,sor_contact_roles --stop-after-init
```

### Step 5: Run Tests
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  --test-enable --stop-after-init --test-tags=sor_contact_roles
```

## Solution 3: One-Liner (After Setup)

Once dependencies are installed, you can use:

```bash
cd /Users/deepkharadi/Documents/BL && \
source env312/bin/activate && \
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  --test-enable --stop-after-init --test-tags=sor_contact_roles
```

## Verify Setup

Check if virtual environment is active:
```bash
which python3
# Should show: /Users/deepkharadi/Documents/BL/env312/bin/python3
```

Check if babel is installed:
```bash
python3 -c "import babel; print('Babel installed:', babel.__version__)"
```

## Common Issues

### Issue: "command not found: createdb"
**Solution**: Install PostgreSQL client tools or use existing database

### Issue: "Database does not exist"
**Solution**: 
```bash
createdb test_db
# Or use existing database name
```

### Issue: "Permission denied"
**Solution**: Check PostgreSQL permissions or use a different database

### Issue: Still getting import errors
**Solution**: 
```bash
source env312/bin/activate
pip install --upgrade -r requirements.txt
```

## Expected Output

When tests run successfully, you should see:
```
test_multiple_contact_types_assignment ... ok
test_subtype_parent_auto_assignment ... ok
...
----------------------------------------------------------------------
Ran 121 tests in X.XXXs

OK
```

## Troubleshooting

If you see errors, check:
1. ✅ Virtual environment is activated (`which python3` shows env312 path)
2. ✅ Dependencies are installed (`pip list | grep babel`)
3. ✅ Database exists (`psql -l | grep test_db`)
4. ✅ Module is installed (`python3 odoo-bin -d test_db -u sor_contact_roles --stop-after-init`)

