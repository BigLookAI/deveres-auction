# SOR Artwork Module - Tests Directory

This directory contains all test files, scripts, and documentation for the SOR Artwork module.

## 📁 Directory Structure

```
tests/
├── __init__.py                          # Test module initialization
├── test_*.py                            # Unit test files (Odoo standard)
│
├── scripts/                             # All test-related scripts
│   ├── populate/                        # Data population scripts
│   │   ├── populate_large_creator_artwork_data.sh
│   │   ├── populate_test_data_standalone.py
│   │   └── run_populate_all_data.sh     # ⭐ Main entry point
│   │
│   ├── verify/                          # Data verification scripts
│   │   └── verify_quick.sh
│   │
│   ├── run/                             # Test runner scripts
│   │   ├── run_all_tests.sh
│   │   ├── run_installation_tests.sh
│   │   └── run_performance_tests.sh
│   │
│   └── utils/                           # Utility scripts
│       ├── clean_duplicates.sh
│       ├── delete_test_data.sh
│       └── view_test_data.sh
│
└── docs/                                # Documentation
    ├── README_QUICK_START.md            # Quick start guide
    └── QUICK_COMMANDS.md                # Command reference
```

## 🚀 Quick Start

### One-Command Setup (Recommended)

```bash
# Populate all test data (all contact types + all product types)
./addons/sor_artwork/tests/scripts/populate/run_populate_all_data.sh test_large_creator_artwork
```

This single command will:
- ✅ Auto-detect virtual environment
- ✅ Create database if needed
- ✅ Install modules if needed
- ✅ Clean duplicates automatically
- ✅ Create all contact types (10 types)
- ✅ Create all product types (4 types)
- ✅ Verify everything
- ✅ Show summary

### View Data in UI

```bash
./addons/sor_artwork/tests/scripts/utils/view_test_data.sh test_large_creator_artwork
```

### Verify Data

```bash
./addons/sor_artwork/tests/scripts/verify/verify_quick.sh test_large_creator_artwork
```

### Run Unit Tests

```bash
# Run all tests
./addons/sor_artwork/tests/scripts/run/run_all_tests.sh test_db

# Run installation tests only
./addons/sor_artwork/tests/scripts/run/run_installation_tests.sh test_db

# Run performance tests only
./addons/sor_artwork/tests/scripts/run/run_performance_tests.sh test_db
```

## 📋 Unit Test Files

All unit test files follow Odoo naming conventions (`test_*.py`) and are located at the root of the `tests/` directory:

- `test_artwork_fields_validations.py` - Field validation tests
- `test_contact_type_system.py` - Contact type system tests
- `test_creator_artwork_relationship.py` - Creator-artwork relationship tests
- `test_data_integrity.py` - Data integrity tests
- `test_module_installation.py` - Module installation tests
- `test_performance.py` - Performance tests
- `test_performance_data.py` - Performance test data generator
- `test_workflow_integration.py` - Workflow integration tests

## 🛠️ Script Categories

### Populate Scripts (`scripts/populate/`)

Scripts for generating test data:

- **`run_populate_all_data.sh`** - Main entry point for data population
- **`populate_large_creator_artwork_data.sh`** - Large-scale data generator
- **`populate_test_data_standalone.py`** - Standalone Python data generator

### Verify Scripts (`scripts/verify/`)

Scripts for verifying test data:

- **`verify_quick.sh`** - Quick data verification and summary

### Run Scripts (`scripts/run/`)

Scripts for running unit tests:

- **`run_all_tests.sh`** - Run all test suites
- **`run_installation_tests.sh`** - Run installation tests only
- **`run_performance_tests.sh`** - Run performance tests only

### Utility Scripts (`scripts/utils/`)

Helper scripts for data management:

- **`clean_duplicates.sh`** - Remove duplicate contacts and products
- **`delete_test_data.sh`** - Delete all test data
- **`view_test_data.sh`** - Start Odoo server to view test data in UI

## 📚 Documentation

See the `docs/` directory for detailed documentation:

- **`README_QUICK_START.md`** - Complete quick start guide with examples
- **`QUICK_COMMANDS.md`** - Quick reference for all commands

## 🔧 Common Tasks

### Clean Database and Repopulate

```bash
# 1. Delete all test data
./addons/sor_artwork/tests/scripts/utils/delete_test_data.sh test_large_creator_artwork

# 2. Populate fresh data
./addons/sor_artwork/tests/scripts/populate/run_populate_all_data.sh test_large_creator_artwork
```

### Clean Duplicates

```bash
./addons/sor_artwork/tests/scripts/utils/clean_duplicates.sh test_large_creator_artwork
```

### Custom Data Counts

```bash
./addons/sor_artwork/tests/scripts/populate/run_populate_all_data.sh test_large_creator_artwork \
  2000 10 500 200 100 100 300 300 200 200 100 100 500 300 300
```

## 📝 Notes

- All scripts use relative paths and will work from any location
- Scripts auto-detect virtual environment (`env312` or `env`)
- Database will be created automatically if it doesn't exist
- Modules will be installed automatically if needed
- All scripts include comprehensive error handling and user feedback

---

**Last Updated**: January 16, 2026

