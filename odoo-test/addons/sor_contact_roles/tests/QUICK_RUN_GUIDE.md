# Quick Test Run Guide

## Simple Commands

### Run Tests with Detailed Report (Recommended)
```bash
cd /Users/deepkharadi/Documents/BL
./addons/sor_contact_roles/tests/run_tests.sh test_db detailed
```

### Run Tests with Simple Output
```bash
./addons/sor_contact_roles/tests/run_tests.sh test_db
# or
./addons/sor_contact_roles/tests/run_tests.sh test_db simple
```

### Show Help
```bash
./addons/sor_contact_roles/tests/run_tests.sh help
```

## What You Get

### Detailed Report Mode (`detailed`)
- ✅ Modules loaded count
- ✅ Each test case as it runs
- ✅ Test summary with statistics
- ✅ Test files breakdown
- ✅ Individual test cases with pass/fail status
- ✅ Final status

### Simple Mode (`simple` or default)
- ✅ Standard Odoo test output
- ✅ Test execution logs
- ✅ Final summary

## Examples

```bash
# Default database (test_db) with detailed report
./addons/sor_contact_roles/tests/run_tests.sh test_db detailed

# Custom database with detailed report
./addons/sor_contact_roles/tests/run_tests.sh my_database detailed

# Simple output mode
./addons/sor_contact_roles/tests/run_tests.sh test_db simple
```

## What the Script Does Automatically

1. ✅ Activates virtual environment
2. ✅ Checks dependencies
3. ✅ Creates database if needed
4. ✅ Installs/upgrades module
5. ✅ Runs tests with your chosen mode
6. ✅ Shows results

## No Manual Commands Needed!

Just run:
```bash
./addons/sor_contact_roles/tests/run_tests.sh test_db detailed
```

That's it! 🎉

