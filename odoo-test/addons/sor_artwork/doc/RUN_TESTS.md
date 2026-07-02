# Running Tests for SOR Artwork Module

## Prerequisites
1. Activate virtual environment: `source env312/bin/activate`
2. Ensure `sor_artwork` module is installed in the database
3. Ensure `sor_contact_roles` module is installed (dependency)

## Run All Tests

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  --test-enable --stop-after-init --test-tags=sor_artwork --http-port=8070
```

## Run Specific Test Files

### Contact Type System Tests
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init \
  --test-tags=sor_artwork/test_contact_type_system --http-port=8070
```

### Creator-Artwork Relationship Tests
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init \
  --test-tags=sor_artwork/test_creator_artwork_relationship --http-port=8070
```

### Artwork Fields and Validations Tests
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init \
  --test-tags=sor_artwork/test_artwork_fields_validations --http-port=8070
```

### Workflow Integration Tests
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init \
  --test-tags=sor_artwork/test_workflow_integration --http-port=8070
```

### Data Integrity Tests
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init \
  --test-tags=sor_artwork/test_data_integrity --http-port=8070
```

## Run with Verbose Output

```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init --test-tags=sor_artwork \
  --log-level=test --http-port=8070
```

## Test Files Overview

| Test File | Description | Test Count |
|-----------|-------------|------------|
| `test_contact_type_system.py` | Unit tests for contact type system | 10+ |
| `test_creator_artwork_relationship.py` | Unit tests for creator-artwork relationship | 8+ |
| `test_artwork_fields_validations.py` | Unit tests for artwork fields and validations | 15+ |
| `test_workflow_integration.py` | Integration tests for complete workflows | 7+ |
| `test_data_integrity.py` | Data integrity and edge case tests | 12+ |
| **TOTAL** | **All US-16 test cases** | **50+** |

## Troubleshooting

### Tests Not Found
- Ensure module is installed: `python3 odoo-bin --addons-path=addons,odoo/addons -d your_db -u sor_artwork --stop-after-init`
- Check that `sor_contact_roles` is installed (dependency)
- Verify test files exist in `addons/sor_artwork/tests/`

### Module Not Installed Error
- Install the module first: `python3 odoo-bin --addons-path=addons,odoo/addons -d your_db -i sor_artwork --stop-after-init`

### Port Already in Use
- Use a different port: `--http-port=8070` (or any available port)

## Expected Output

When tests run successfully, you should see:
```
Starting TestContactTypeSystem.test_contact_type_creation ... ok
Starting TestContactTypeSystem.test_contact_type_assignment_single ... ok
...
Ran X tests in Y seconds
```

## Notes

- All tests use `@tagged('post_install', '-at_install')` decorator
- Tests require `sor_contact_roles` module to be installed
- Tests clean up after themselves (no manual cleanup needed)
- Some tests check for optional features (e.g., `artwork_ids` field) and will pass even if not implemented

