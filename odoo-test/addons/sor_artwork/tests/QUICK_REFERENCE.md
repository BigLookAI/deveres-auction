# Quick Reference - Test Commands

## 🚀 Most Common Commands

### Populate Test Data
```bash
# One command to populate everything
./addons/sor_artwork/tests/scripts/populate/run_populate_all_data.sh test_large_creator_artwork
```

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
# All tests
./addons/sor_artwork/tests/scripts/run/run_all_tests.sh test_db

# Installation tests only
./addons/sor_artwork/tests/scripts/run/run_installation_tests.sh test_db

# Performance tests only
./addons/sor_artwork/tests/scripts/run/run_performance_tests.sh test_db
```

### Clean & Manage Data
```bash
# Clean duplicates
./addons/sor_artwork/tests/scripts/utils/clean_duplicates.sh test_large_creator_artwork

# Delete all test data
./addons/sor_artwork/tests/scripts/utils/delete_test_data.sh test_large_creator_artwork
```

## 📁 File Locations

- **Unit Tests**: `tests/test_*.py`
- **Populate Scripts**: `tests/scripts/populate/`
- **Verify Scripts**: `tests/scripts/verify/`
- **Test Runners**: `tests/scripts/run/`
- **Utilities**: `tests/scripts/utils/`
- **Documentation**: `tests/docs/`

## 📖 Full Documentation

See `tests/README.md` for complete documentation.

