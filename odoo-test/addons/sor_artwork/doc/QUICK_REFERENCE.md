# Quick Test Runner Reference

## Command to Run Tests with Full Details

```bash
cd /Users/deepkharadi/Documents/BL
./addons/sor_artwork/tests/run_tests_detailed.sh test_db
```

## What You'll See

The output shows:

1. **Module Name** - Each test module is clearly labeled
2. **Test Case Name** - Full test class and method name
3. **Status** - ✓ PASSED, ✗ FAILED, or ⚠ ERROR for each test
4. **Module Summary** - Count of tests per module with pass/fail/error breakdown
5. **Overall Summary** - Total statistics across all modules

## Example Output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Module: Contact Type System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [  1] TestContactTypeSystem.test_contact_type_creation             ✓ PASSED
  [  2] TestContactTypeSystem.test_contact_type_assignment_single    ✓ PASSED
  [  3] TestContactTypeSystem.test_contact_type_assignment_multiple  ✓ PASSED
  ...

  Summary: Total=11 | Passed=11 | Failed=0 | Errors=0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Module: Creator-Artwork Relationship
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [  1] TestCreatorArtworkRelationship.test_artwork_creation_with_creator  ✓ PASSED
  ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Tests: 57
✓ Passed:   57

✅ All tests passed!
```

## Test Modules

1. **Contact Type System** (11 tests)
2. **Creator-Artwork Relationship** (8 tests)
3. **Artwork Fields & Validations** (17 tests)
4. **Workflow Integration** (7 tests)
5. **Data Integrity & Edge Cases** (14 tests)

**Total: 57 tests**

