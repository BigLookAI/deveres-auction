# Detailed Test Report Guide

## Quick Command

Run tests with detailed reporting:

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 addons/sor_contact_roles/tests/run_tests_detailed.py test_db 8070
```

## What the Report Shows

### 1. **Modules Loaded**
- Shows how many modules were loaded during test execution
- Initial load: Core modules
- Full load: All dependencies

### 2. **Test Execution**
- Lists each test case as it runs
- Shows test class and method name
- Real-time progress indicator

### 3. **Test Summary**
- **Total Tests**: Number of tests executed
- **Execution Time**: How long tests took
- **Database Queries**: Number of SQL queries executed
- **Test Results**: Passed/Failed/Errors/Skipped counts

### 4. **Test Files Breakdown**
- Shows statistics for each test file:
  - Total tests per file
  - Passed count
  - Failed count
  - Errors count
  - Skipped count

### 5. **Individual Test Cases**
- Complete list of all test cases
- Status for each test: [PASS], [FAIL], [ERROR], [SKIP]
- Organized by test class

### 6. **Final Status**
- Overall pass/fail status
- Clear visual indicator

## Example Output

```
============================================================
          SOR Contact Roles - Detailed Test Report          
============================================================

Modules Loaded: 63
  - Initial load: 1
  - Full load: 62

Test Statistics:
  Total Tests: 135
  Execution Time: 1.96s
  Database Queries: 2866

Test Results:
  ✓ Passed: 119

Test Files Breakdown:
✓ TestResPartnerContactTypes
    Tests: 9 | Passed: 9 | Failed: 0 | Errors: 0 | Skipped: 0
✓ TestResPartnerCreatorFields
    Tests: 10 | Passed: 10 | Failed: 0 | Errors: 0 | Skipped: 0
...

Individual Test Cases:
TestResPartnerContactTypes:
  ✓ test_computed_fields_update                        [PASS]
  ✓ test_contact_without_types                         [PASS]
  ...
```

## Command Options

```bash
# Default database (test_db) and port (8070)
python3 addons/sor_contact_roles/tests/run_tests_detailed.py

# Custom database
python3 addons/sor_contact_roles/tests/run_tests_detailed.py my_database

# Custom database and port
python3 addons/sor_contact_roles/tests/run_tests_detailed.py my_database 8080
```

## Test Files Included

1. **TestResPartnerContactTypes** (9 tests)
   - Basic contact type assignment tests

2. **TestResPartnerCreatorFields** (10 tests)
   - Creator-specific field tests

3. **TestResPartnerCustomerFields** (9 tests)
   - Customer-specific field tests

4. **TestResPartnerExtended** (49 tests)
   - Extended partner functionality tests

5. **TestResPartnerIntegration** (6 tests)
   - Integration workflow tests

6. **TestResPartnerMultiCompany** (3 tests)
   - Multi-company support tests

7. **TestSorContactSocialMedia** (14 tests)
   - Social media model tests

8. **TestSorContactType** (19 tests)
   - Contact type model tests

**Total: 119 test cases**

## Troubleshooting

### Issue: Script not found
```bash
# Make sure you're in the project root
cd /Users/deepkharadi/Documents/BL

# Check if script exists
ls -la addons/sor_contact_roles/tests/run_tests_detailed.py
```

### Issue: Virtual environment not activated
```bash
source env312/bin/activate
```

### Issue: Port already in use
```bash
# Use a different port
python3 addons/sor_contact_roles/tests/run_tests_detailed.py test_db 8080
```

## Alternative: Simple Test Run

If you just want basic output:

```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  --http-port=8070 --test-enable --stop-after-init \
  --test-tags=sor_contact_roles --log-level=test
```

