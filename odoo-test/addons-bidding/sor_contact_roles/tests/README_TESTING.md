# How to Run Test Cases for SOR Contact Roles Module

## Prerequisites

1. Odoo instance running (version 19.0)
2. Database with `sor_contact_roles` module installed
3. Test database (recommended) or development database

---

## Method 1: Run Tests via Odoo Command Line (Recommended)

### Run All Tests in the Module

```bash
# From your Odoo root directory
./odoo-bin -c odoo.conf -d your_database_name --test-enable --stop-after-init --log-level=test
```

### Run Specific Test File

```bash
# Run only contact type model tests
./odoo-bin -c odoo.conf -d your_database_name --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_sor_contact_type

# Run only partner tests
./odoo-bin -c odoo.conf -d your_database_name --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_res_partner

# Run only social media tests
./odoo-bin -c odoo.conf -d your_database_name --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_sor_contact_social_media
```

### Run Tests with Specific Tags

```bash
# Run only post_install tests (all our tests use this tag)
./odoo-bin -c odoo.conf -d your_database_name --test-enable --stop-after-init \
  --test-tags=post_install
```

### Run a Single Test Method

```bash
# Run specific test method
./odoo-bin -c odoo.conf -d your_database_name --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_res_partner.TestResPartnerContactTypes.test_multiple_contact_types_assignment
```

---

## Method 2: Run Tests via Odoo Shell (Interactive)

### Start Odoo Shell

```bash
./odoo-bin shell -d your_database_name
```

### Run Tests in Shell

```python
# Import test loader
from odoo.tests.loader import get_test_modules
from odoo.tests.suite import OdooSuite
from odoo.tests.runner import OdooTestRunner

# Load and run all tests for sor_contact_roles
import odoo.tests.loader as loader
import odoo.tests.runner as runner

# Get test cases
test_module = __import__('odoo.addons.sor_contact_roles.tests', fromlist=[''])
test_cases = loader.get_module_test_cases(test_module)

# Run tests
suite = OdooSuite()
for test_case in test_cases:
    suite.addTest(test_case)

# Run the suite
test_runner = runner.OdooTestRunner(verbosity=2)
result = test_runner.run(suite)
```

---

## Method 3: Run Tests via Python unittest (Direct)

### Run All Tests

```bash
# From your Odoo root directory
python3 -m pytest odoo/addons/sor_contact_roles/tests/ -v

# Or using unittest
python3 -m unittest discover -s odoo/addons/sor_contact_roles/tests/ -p "test_*.py" -v
```

### Run Specific Test File

```bash
python3 -m unittest odoo.addons.sor_contact_roles.tests.test_sor_contact_type -v
python3 -m unittest odoo.addons.sor_contact_roles.tests.test_res_partner -v
```

### Run Specific Test Class

```bash
python3 -m unittest odoo.addons.sor_contact_roles.tests.test_res_partner.TestResPartnerContactTypes -v
```

### Run Specific Test Method

```bash
python3 -m unittest odoo.addons.sor_contact_roles.tests.test_res_partner.TestResPartnerContactTypes.test_multiple_contact_types_assignment -v
```

---

## Method 4: Run Tests via Odoo Web Interface (if available)

1. Go to **Settings** → **Technical** → **Database Structure** → **Tests**
2. Search for `sor_contact_roles`
3. Click on test cases to run them

---

## Method 5: Run Tests Programmatically in Odoo

### Create a Script to Run Tests

Create a file `run_tests.py`:

```python
#!/usr/bin/env python3
import odoo
from odoo import api, SUPERUSER_ID

# Initialize Odoo
odoo.tools.config.parse_config(['-c', 'odoo.conf'])
odoo.service.db.init()
odoo.registry.Registry.new('your_database_name')

# Run tests
import odoo.tests.loader as loader
import odoo.tests.runner as runner
from odoo.tests.suite import OdooSuite

# Load test module
test_module = __import__('odoo.addons.sor_contact_roles.tests', fromlist=[''])
test_cases = loader.get_module_test_cases(test_module)

# Create suite
suite = OdooSuite()
for test_case in test_cases:
    suite.addTest(test_case)

# Run tests
test_runner = runner.OdooTestRunner(verbosity=2)
result = test_runner.run(suite)

# Print results
print(f"\nTests run: {result.testsRun}")
print(f"Failures: {len(result.failures)}")
print(f"Errors: {len(result.errors)}")
print(f"Skipped: {len(result.skipped)}")
```

Run it:
```bash
python3 run_tests.py
```

---

## Quick Test Commands

### Test All Contact Type Model Tests
```bash
./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_sor_contact_type
```

### Test All Partner Tests
```bash
./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_res_partner
```

### Test All Social Media Tests
```bash
./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_sor_contact_social_media
```

### Test Integration Tests
```bash
./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_res_partner_integration
```

### Test Everything in Module
```bash
./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
  --test-tags=sor_contact_roles
```

---

## Understanding Test Output

### Successful Test
```
test_multiple_contact_types_assignment ... ok
```

### Failed Test
```
test_multiple_contact_types_assignment ... FAIL

======================================================================
FAIL: test_multiple_contact_types_assignment (odoo.addons.sor_contact_roles.tests.test_res_partner.TestResPartnerContactTypes)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
AssertionError: ...
```

### Error in Test
```
test_multiple_contact_types_assignment ... ERROR

======================================================================
ERROR: test_multiple_contact_types_assignment (odoo.addons.sor_contact_roles.tests.test_res_partner.TestResPartnerContactTypes)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
```

---

## Test Coverage Report

To generate a coverage report:

```bash
# Install coverage
pip install coverage

# Run tests with coverage
coverage run --source=addons/sor_contact_roles --omit='*/tests/*' \
  ./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
  --test-tags=sor_contact_roles

# Generate report
coverage report
coverage html  # Generates HTML report in htmlcov/
```

---

## Common Issues and Solutions

### Issue: "Module not found"
**Solution**: Make sure the module is installed in the database:
```bash
./odoo-bin -c odoo.conf -d your_db -i sor_contact_roles --stop-after-init
```

### Issue: "Database does not exist"
**Solution**: Create a test database:
```bash
createdb test_db
./odoo-bin -c odoo.conf -d test_db -i base --stop-after-init
```

### Issue: "Tests not running"
**Solution**: Check that tests are tagged correctly. All our tests use `@tagged('post_install', '-at_install')`

### Issue: "Permission denied"
**Solution**: Make sure you have proper database access and Odoo user permissions

---

## Recommended Workflow

1. **Create a test database** (separate from production):
   ```bash
   createdb test_db
   ./odoo-bin -c odoo.conf -d test_db -i base,sor_contact_roles --stop-after-init
   ```

2. **Run all tests** to verify everything works:
   ```bash
   ./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
     --test-tags=sor_contact_roles
   ```

3. **Run specific test** when debugging:
   ```bash
   ./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
     --test-tags=sor_contact_roles/test_res_partner.TestResPartnerContactTypes.test_multiple_contact_types_assignment
   ```

4. **Check test output** for failures and fix issues

---

## Test File Structure

```
addons/sor_contact_roles/tests/
├── __init__.py                          # Test module initialization
├── test_sor_contact_type.py             # Contact type model tests (12 tests)
├── test_res_partner.py                  # Basic partner tests (9 tests)
├── test_res_partner_extended.py         # Extended partner tests (60+ tests)
├── test_res_partner_creator_fields.py   # Creator fields tests (10 tests)
├── test_res_partner_customer_fields.py   # Customer fields tests (9 tests)
├── test_sor_contact_social_media.py     # Social media tests (14 tests)
└── test_res_partner_integration.py      # Integration tests (5 tests)
```

**Total: 121+ test cases**

---

## Tips

1. **Use a dedicated test database** - Never run tests on production data
2. **Run tests before committing** - Ensure all tests pass before pushing code
3. **Run specific tests during development** - Faster feedback loop
4. **Check test logs** - Odoo test output shows detailed information
5. **Use verbose mode** - Add `-v` or `--log-level=test` for detailed output

---

## Example: Complete Test Run

```bash
# 1. Create test database
createdb test_db

# 2. Install base and module
./odoo-bin -c odoo.conf -d test_db -i base,sor_contact_roles --stop-after-init

# 3. Run all tests
./odoo-bin -c odoo.conf -d test_db --test-enable --stop-after-init \
  --test-tags=sor_contact_roles --log-level=test

# 4. Check output for results
# Look for: "Tests run: 121, Failures: 0, Errors: 0"
```

---

For more information, see Odoo Testing Documentation:
https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html

