# Quick Test Runner - SOR Artwork Module

## Quick Start

### Option 1: Detailed Python Script (Recommended)
Shows color-coded output with results for each test case:

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 addons/sor_artwork/tests/run_tests_detailed.py test_db
```

### Option 2: Verbose Shell Script
Shows test results with color-coded output:

```bash
cd /Users/deepkharadi/Documents/BL
./addons/sor_artwork/tests/run_tests_verbose.sh test_db
```

### Option 3: Standard Odoo Command with Filtering
Shows all test output with filtering:

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  --test-enable --stop-after-init --test-tags=sor_artwork \
  --log-level=test --http-port=8070 2>&1 | \
  grep -E "(Starting|ok|FAIL|ERROR|Ran|sor_artwork|failed)" | \
  sed 's/Starting /▶ /; s/\.\.\. ok/✓ PASSED/; s/FAIL:/✗ FAILED:/; s/ERROR:/⚠ ERROR:/'
```

## Test Modules

The test suite includes 5 test modules:

1. **Contact Type System Tests** (`test_contact_type_system.py`)
   - Contact type creation and assignment
   - Multiple contact types
   - Computed fields
   - Field visibility

2. **Creator-Artwork Relationship Tests** (`test_creator_artwork_relationship.py`)
   - Artwork creation with creator
   - Domain filters
   - Reverse relationships

3. **Artwork Fields & Validations Tests** (`test_artwork_fields_validations.py`)
   - All artwork fields
   - Creation year validation
   - Dimensions validation
   - Type/subtype validation

4. **Workflow Integration Tests** (`test_workflow_integration.py`)
   - Complete workflows
   - End-to-end scenarios
   - Multiple artworks/creators

5. **Data Integrity & Edge Cases Tests** (`test_data_integrity.py`)
   - Edge cases
   - Boundary values
   - Error handling

## Output Format

The detailed runner shows:
- ✅ **Green checkmark (✓)**: Test passed
- ❌ **Red X (✗)**: Test failed
- ⚠️ **Red warning (⚠)**: Test error
- ▶️ **Yellow arrow (▶)**: Test running

## Example Output

```
============================================================
SOR Artwork Module - Detailed Test Runner
============================================================
Database: test_db

────────────────────────────────────────────────────────────
Running All Tests
────────────────────────────────────────────────────────────

  ▶ Contact Type System Tests :: test_contact_type_creation
  ✓ Contact Type System Tests :: test_contact_type_creation
  ▶ Contact Type System Tests :: test_contact_type_assignment_single
  ✓ Contact Type System Tests :: test_contact_type_assignment_single
  ...

────────────────────────────────────────────────────────────
Test Results by Module
────────────────────────────────────────────────────────────

Contact Type System Tests
  Total Tests: 10
  Passed: 10
  Failed: 0
  Errors: 0

Creator-Artwork Relationship Tests
  Total Tests: 8
  Passed: 8
  Failed: 0
  Errors: 0

...

────────────────────────────────────────────────────────────
Final Summary
────────────────────────────────────────────────────────────
Total Tests: 57
Passed: 57
Failed: 0
Errors: 0

Success Rate: 100.0%

✅ All tests passed! ✓
```

## Run Specific Test Module

To run a specific test module:

```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  --test-enable --stop-after-init \
  --test-tags=sor_artwork/test_contact_type_system \
  --log-level=test --http-port=8070
```

## Troubleshooting

### Tests not found
- Ensure module is installed: `python3 odoo-bin ... -u sor_artwork --stop-after-init`
- Check database name is correct

### Port already in use
- Use different port: `--http-port=8071`

### Import errors
- Activate virtual environment: `source env312/bin/activate`
- Ensure dependencies are installed

