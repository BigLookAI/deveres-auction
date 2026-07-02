# Quick Test Guide - SOR Contact Roles

## 🚀 Quick Start

### Run All Tests (121+ test cases)
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
  --test-enable --stop-after-init --test-tags=sor_contact_roles
```

## 📋 Test Files Overview

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_sor_contact_type.py` | 12 | Contact type model tests |
| `test_res_partner.py` | 9 | Basic partner assignment tests |
| `test_res_partner_extended.py` | 60+ | Extended partner tests |
| `test_res_partner_creator_fields.py` | 10 | Creator-specific fields |
| `test_res_partner_customer_fields.py` | 9 | Customer-specific fields |
| `test_sor_contact_social_media.py` | 14 | Social media model tests |
| `test_res_partner_integration.py` | 5 | Integration workflows |
| **TOTAL** | **121+** | **All US-10 test cases** |

## 🎯 Common Commands

### Run Specific Test File
```bash
# Contact type model
python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
  --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_sor_contact_type

# Partner tests
python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
  --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_res_partner

# Social media
python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
  --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_sor_contact_social_media
```

### Run Single Test Method
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
  --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_res_partner.TestResPartnerContactTypes.test_multiple_contact_types_assignment
```

### Run with Verbose Output
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
  --test-enable --stop-after-init --test-tags=sor_contact_roles \
  --log-level=test
```

## ✅ Expected Output

### Success
```
test_multiple_contact_types_assignment ... ok
test_subtype_parent_auto_assignment ... ok
...
----------------------------------------------------------------------
Ran 121 tests in X.XXXs

OK
```

### Failure
```
test_multiple_contact_types_assignment ... FAIL
...
AssertionError: ...
```

## 🔍 Test Categories

- ✅ **Contact Type Model** - Model constraints, validation
- ✅ **ResPartner Assignment** - Type assignment, multi-assignment
- ✅ **Computed Fields** - All is_* helper fields
- ✅ **Sub-Type Relationships** - Parent-child hierarchy
- ✅ **Multi-Company** - Cross-company support
- ✅ **Creator Fields** - Biography, birth_date, nationality, etc.
- ✅ **Customer Fields** - Collection focus, preferred artists
- ✅ **Social Media** - URL computation, unique constraints
- ✅ **OnChange Logic** - Auto-selection of sub-types
- ✅ **Validation** - Constraints and rules
- ✅ **Backward Compatibility** - Legacy support
- ✅ **Integration** - Complete workflows

## 📝 Notes

- All tests use `@tagged('post_install', '-at_install')`
- Tests require module to be installed first
- Use a test database (not production)
- Tests clean up after themselves

## 🐛 Troubleshooting

**Module not found?**
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_db \
  -i sor_contact_roles --stop-after-init
```

**Database doesn't exist?**
```bash
createdb test_db
```

**Tests not running?**
- Check module is installed
- Verify database exists
- Check addons path is correct

For detailed information, see `README_TESTING.md`

