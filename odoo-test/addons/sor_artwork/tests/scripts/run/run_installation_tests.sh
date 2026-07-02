#!/bin/bash
# Installation Test Runner - Tests module installation in clean environment

DB_NAME=${1:-test_installation_db}
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
echo "SOR Artwork Module - Installation Test Runner"
echo "============================================================"
echo "Database: $DB_NAME"
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
    > /tmp/sor_artwork_install_base.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install base dependencies"
    echo "Check log: /tmp/sor_artwork_install_base.log"
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
    > /tmp/sor_artwork_install_contact_roles.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install sor_contact_roles dependency"
    echo "Check log: /tmp/sor_artwork_install_contact_roles.log"
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
    > /tmp/sor_artwork_install.log 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install sor_artwork module"
    echo "Check log: /tmp/sor_artwork_install.log"
    exit 1
fi
echo "sor_artwork module installed successfully."
echo ""

echo "Step 4: Running installation tests..."
python3 odoo-bin \
    --addons-path=addons,odoo/addons \
    -d "$DB_NAME" \
    --test-enable \
    --stop-after-init \
    --test-tags=+sor_artwork.test_module_installation \
    --log-level=test \
    --http-port=8070 \
    2>&1 | tee /tmp/sor_artwork_installation_tests.log

TEST_EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "============================================================"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ Installation tests PASSED"
    echo "============================================================"
    echo ""
    echo "Installation test summary:"
    echo "- Module installed successfully"
    echo "- All models created"
    echo "- All views accessible"
    echo "- Security rules loaded"
    echo "- Dependencies resolved"
    echo ""
    echo "Full test log: /tmp/sor_artwork_installation_tests.log"
    exit 0
else
    echo "❌ Installation tests FAILED"
    echo "============================================================"
    echo ""
    echo "Check the following logs for details:"
    echo "- Installation log: /tmp/sor_artwork_install.log"
    echo "- Test log: /tmp/sor_artwork_installation_tests.log"
    exit 1
fi

