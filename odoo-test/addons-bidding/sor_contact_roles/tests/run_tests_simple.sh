#!/bin/bash
# Simple test runner - handles errors gracefully

cd /Users/deepkharadi/Documents/BL || exit 1

# Activate virtual environment
source env312/bin/activate

# Database name
DB_NAME="${1:-test_db}"

echo "=== Running SOR Contact Roles Tests ==="
echo "Database: $DB_NAME"
echo ""

# Run tests directly
python3 odoo-bin --addons-path=addons,odoo/addons -d "$DB_NAME" \
    --test-enable --stop-after-init \
    --test-tags=sor_contact_roles \
    --log-level=test

echo ""
echo "=== Tests Complete ==="

