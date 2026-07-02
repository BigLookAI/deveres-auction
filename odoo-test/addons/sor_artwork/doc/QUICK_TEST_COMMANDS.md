# Quick Test Commands - Quick Reference

## Setup (Run Once)

```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
```

## Test Commands (Run in Order)

### 1. Installation Tests (Fast - ~30 seconds)
```bash
./addons/sor_artwork/tests/run_installation_tests.sh test_install_verify
```
**Expected**: ✅ Installation tests PASSED (7 tests)

---

### 2. Performance Tests (Slow - 5-10 minutes)
```bash
./addons/sor_artwork/tests/run_performance_tests.sh test_perf_verify
```
**Expected**: ✅ Performance tests PASSED (6 tests)
- List view: < 2 seconds
- Search: < 1 second

---

### 3. All Tests Without Performance (Fast - ~1 minute)
```bash
./addons/sor_artwork/tests/run_all_tests.sh test_all_verify
```
**Expected**: ✅ All test suites PASSED (except performance)

---

### 4. All Tests With Performance (Complete - 10-15 minutes)
```bash
./addons/sor_artwork/tests/run_all_tests.sh test_full_verify yes
```
**Expected**: ✅ ALL TESTS PASSED (85 tests total)

---

## Manual Odoo Command (Alternative)

### Setup Database
```bash
createdb test_manual
python3 odoo-bin --addons-path=addons,odoo/addons -d test_manual -i base,product,sor_contact_roles,sor_artwork --stop-after-init
```

### Run All Tests
```bash
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d test_manual \
    --test-enable \
    --stop-after-init \
    --test-tags=sor_artwork \
    --log-level=test
```

**Expected Output**:
```
sor_artwork: 85 tests 5.12s 3977 queries
0 failed, 0 error(s) of 71 tests
```

---

## Verify Results

### Check Test Counts
```bash
# Should show: 85 tests, 0 failed
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d test_manual \
    --test-enable \
    --stop-after-init \
    --test-tags=sor_artwork \
    --log-level=warn \
    2>&1 | grep -E "(tests|PASSED|FAILED)"
```

### Check Logs
```bash
# Installation tests
cat /tmp/sor_artwork_installation_tests.log | grep -E "(PASSED|FAILED|test_module_installation)"

# Performance tests
cat /tmp/sor_artwork_performance_tests.log | grep -E "(Performance|List view|Search|seconds)"
```

---

## Cleanup

```bash
dropdb test_install_verify test_perf_verify test_all_verify test_full_verify test_manual
rm -f /tmp/sor_artwork_*.log
```

---

## Expected Results Summary

| Test Suite | Tests | Status | Time |
|------------|-------|--------|------|
| Installation | 7 | ✅ PASS | ~30s |
| Performance | 6 | ✅ PASS | ~5-10min |
| Unit Tests | ~20 | ✅ PASS | ~1s |
| Integration | ~10 | ✅ PASS | ~1s |
| Relationship | ~8 | ✅ PASS | ~1s |
| Data Integrity | ~15 | ✅ PASS | ~1s |
| Contact Type | ~10 | ✅ PASS | ~1s |
| **TOTAL** | **85** | **✅ PASS** | **~10-15min** |

---

## One-Liner Complete Test

```bash
cd /Users/deepkharadi/Documents/BL && \
source env312/bin/activate && \
./addons/sor_artwork/tests/run_all_tests.sh test_complete yes
```

