#!/bin/bash
# Comprehensive Test Runner - Runs all test suites

DB_NAME=${1:-test_all_db}
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../../../../.." && pwd )"

cd "$PROJECT_ROOT"

# Activate virtual environment if it exists
if [ -d "env312" ]; then
    source env312/bin/activate
elif [ -d "env" ]; then
    source env/bin/activate
fi

echo "============================================================"
echo "SOR Artwork Module - Comprehensive Test Runner"
echo "============================================================"
echo "Database: $DB_NAME"
echo ""
echo "This will run all test suites:"
echo "  1. Installation tests"
echo "  2. Unit tests"
echo "  3. Integration tests"
echo "  4. Performance tests (optional - takes longer)"
echo ""

# Check if performance tests should be run
RUN_PERFORMANCE=${2:-no}
if [ "$RUN_PERFORMANCE" = "yes" ] || [ "$RUN_PERFORMANCE" = "y" ]; then
    echo "Performance tests will be included (this will take 10-15 minutes)"
    echo ""
else
    echo "Performance tests will be SKIPPED (use 'yes' as second argument to include)"
    echo ""
fi

# Check if database exists
if ! psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    echo "Creating database: $DB_NAME"
    createdb "$DB_NAME" 2>/dev/null || {
        echo "Error: Could not create database. Please create it manually or use existing database."
        exit 1
    }
    echo "Database created successfully."
    echo ""
fi

# Track overall results
OVERALL_SUCCESS=true
TEST_RESULTS=""

# Function to run tests and track results
run_test_suite() {
    local suite_name=$1
    local test_tags=$2
    local log_file=$3
    
    echo "============================================================"
    echo "Running: $suite_name"
    echo "============================================================"
    echo ""
    
    python3 odoo-bin \
        --addons-path=addons,odoo/addons \
        -d "$DB_NAME" \
        --test-enable \
        --stop-after-init \
        --test-tags="$test_tags" \
        --log-level=test \
        --http-port=8070 \
        > "$log_file" 2>&1
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✅ $suite_name: PASSED"
        TEST_RESULTS="${TEST_RESULTS}✅ $suite_name: PASSED\n"
    else
        echo "❌ $suite_name: FAILED"
        TEST_RESULTS="${TEST_RESULTS}❌ $suite_name: FAILED\n"
        OVERALL_SUCCESS=false
    fi
    
    echo "Log: $log_file"
    echo ""
    return $exit_code
}

# Step 1: Install base dependencies
echo "Step 1: Installing base dependencies..."
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d "$DB_NAME" \
    -i base,product \
    --stop-after-init \
    --log-level=warn \
    --http-port=8070 \
    > /tmp/sor_artwork_all_install_base.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install base dependencies"
    exit 1
fi

# Step 2: Install sor_contact_roles
echo "Step 2: Installing sor_contact_roles..."
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d "$DB_NAME" \
    -i sor_contact_roles \
    --stop-after-init \
    --log-level=warn \
    --http-port=8070 \
    > /tmp/sor_artwork_all_install_contact_roles.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install sor_contact_roles"
    exit 1
fi

# Step 3: Install sor_artwork
echo "Step 3: Installing sor_artwork module..."
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d "$DB_NAME" \
    -i sor_artwork \
    --stop-after-init \
    --log-level=warn \
    --http-port=8070 \
    > /tmp/sor_artwork_all_install.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install sor_artwork"
    exit 1
fi

echo ""
echo "============================================================"
echo "Starting Test Suites"
echo "============================================================"
echo ""

# Run installation tests
run_test_suite \
    "Installation Tests" \
    "+sor_artwork.test_module_installation" \
    "/tmp/sor_artwork_all_installation.log"

# Run unit tests (field validations)
run_test_suite \
    "Unit Tests (Field Validations)" \
    "+sor_artwork.test_artwork_fields_validations" \
    "/tmp/sor_artwork_all_unit.log"

# Run integration tests
run_test_suite \
    "Integration Tests (Workflow)" \
    "+sor_artwork.test_workflow_integration" \
    "/tmp/sor_artwork_all_integration.log"

# Run relationship tests
run_test_suite \
    "Relationship Tests" \
    "+sor_artwork.test_creator_artwork_relationship" \
    "/tmp/sor_artwork_all_relationship.log"

# Run data integrity tests
run_test_suite \
    "Data Integrity Tests" \
    "+sor_artwork.test_data_integrity" \
    "/tmp/sor_artwork_all_data_integrity.log"

# Run contact type system tests
run_test_suite \
    "Contact Type System Tests" \
    "+sor_artwork.test_contact_type_system" \
    "/tmp/sor_artwork_all_contact_type.log"

# Run performance tests (optional)
if [ "$RUN_PERFORMANCE" = "yes" ] || [ "$RUN_PERFORMANCE" = "y" ]; then
    echo "WARNING: Performance tests will create 1000+ records and take 10-15 minutes"
    echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
    sleep 5
    
    run_test_suite \
        "Performance Tests" \
        "+sor_artwork.test_performance" \
        "/tmp/sor_artwork_all_performance.log"
else
    echo "Skipping performance tests (use 'yes' as second argument to include)"
    TEST_RESULTS="${TEST_RESULTS}⏭️  Performance Tests: SKIPPED\n"
fi

# Print summary
echo ""
echo "============================================================"
echo "Test Summary"
echo "============================================================"
echo ""
echo -e "$TEST_RESULTS"
echo ""

if [ "$OVERALL_SUCCESS" = true ]; then
    echo "============================================================"
    echo "✅ ALL TESTS PASSED"
    echo "============================================================"
    echo ""
    echo "All test suites completed successfully!"
    echo ""
    echo "Test logs:"
    echo "  - Installation: /tmp/sor_artwork_all_installation.log"
    echo "  - Unit: /tmp/sor_artwork_all_unit.log"
    echo "  - Integration: /tmp/sor_artwork_all_integration.log"
    echo "  - Relationship: /tmp/sor_artwork_all_relationship.log"
    echo "  - Data Integrity: /tmp/sor_artwork_all_data_integrity.log"
    echo "  - Contact Type: /tmp/sor_artwork_all_contact_type.log"
    if [ "$RUN_PERFORMANCE" = "yes" ] || [ "$RUN_PERFORMANCE" = "y" ]; then
        echo "  - Performance: /tmp/sor_artwork_all_performance.log"
    fi
    echo ""
    exit 0
else
    echo "============================================================"
    echo "❌ SOME TESTS FAILED"
    echo "============================================================"
    echo ""
    echo "Check the test logs above for details."
    echo ""
    exit 1
fi

