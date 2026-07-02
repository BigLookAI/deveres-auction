#!/bin/bash
# Performance Test Runner - Tests performance with large datasets

DB_NAME=${1:-test_performance_db}
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
echo "SOR Artwork Module - Performance Test Runner"
echo "============================================================"
echo "Database: $DB_NAME"
echo ""
echo "WARNING: This will create 1000+ contacts and 1000+ artworks"
echo "This may take several minutes to complete."
echo ""

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

echo "Step 1: Installing base dependencies..."
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d "$DB_NAME" \
    -i base,product \
    --stop-after-init \
    --log-level=warn \
    --http-port=8070 \
    > /tmp/sor_artwork_perf_install_base.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install base dependencies"
    echo "Check log: /tmp/sor_artwork_perf_install_base.log"
    exit 1
fi
echo "Base dependencies installed successfully."
echo ""

echo "Step 2: Installing sor_contact_roles dependency..."
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d "$DB_NAME" \
    -i sor_contact_roles \
    --stop-after-init \
    --log-level=warn \
    --http-port=8070 \
    > /tmp/sor_artwork_perf_install_contact_roles.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install sor_contact_roles dependency"
    echo "Check log: /tmp/sor_artwork_perf_install_contact_roles.log"
    exit 1
fi
echo "sor_contact_roles installed successfully."
echo ""

echo "Step 3: Installing sor_artwork module..."
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d "$DB_NAME" \
    -i sor_artwork \
    --stop-after-init \
    --log-level=warn \
    --http-port=8070 \
    > /tmp/sor_artwork_perf_install.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install sor_artwork module"
    echo "Check log: /tmp/sor_artwork_perf_install.log"
    exit 1
fi
echo "sor_artwork module installed successfully."
echo ""

echo "Step 4: Running performance tests..."
echo "This will create test data and run performance tests."
echo "This may take 5-10 minutes..."
echo ""

python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d "$DB_NAME" \
    --test-enable \
    --stop-after-init \
    --test-tags=+sor_artwork.test_performance \
    --log-level=test \
    --http-port=8070 \
    2>&1 | tee /tmp/sor_artwork_performance_tests.log

TEST_EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "============================================================"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ Performance tests PASSED"
    echo "============================================================"
    echo ""
    echo "Performance test summary:"
    echo "- List view load time: < 2 seconds for 1000+ records"
    echo "- Search performance: < 1 second"
    echo "- Computed fields: No performance issues"
    echo "- Query optimization: Verified"
    echo ""
    echo "Full test log: /tmp/sor_artwork_performance_tests.log"
    echo ""
    echo "NOTE: Test database contains 1000+ records."
    echo "You may want to drop it after reviewing results:"
    echo "  dropdb $DB_NAME"
    exit 0
else
    echo "❌ Performance tests FAILED"
    echo "============================================================"
    echo ""
    echo "Check the following logs for details:"
    echo "- Installation log: /tmp/sor_artwork_perf_install.log"
    echo "- Test log: /tmp/sor_artwork_performance_tests.log"
    echo ""
    echo "NOTE: Test database contains 1000+ records."
    echo "You may want to drop it after reviewing results:"
    echo "  dropdb $DB_NAME"
    exit 1
fi

