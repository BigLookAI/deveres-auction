#!/bin/bash
# Script to run SOR Contact Roles tests

# Don't exit on error - we want to handle errors gracefully
set +e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to show usage
show_usage() {
    echo -e "${CYAN}Usage:${NC}"
    echo -e "  $0 [database] [mode]"
    echo ""
    echo -e "${CYAN}Modes:${NC}"
    echo -e "  ${GREEN}default${NC} or ${GREEN}simple${NC}  - Run tests with standard output"
    echo -e "  ${GREEN}detailed${NC} or ${GREEN}report${NC}  - Run tests with detailed report"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo -e "  $0 test_db                    # Run with default output"
    echo -e "  $0 test_db detailed           # Run with detailed report"
    echo -e "  $0 test_db report             # Same as detailed"
    echo -e "  $0 my_db simple               # Run with simple output"
}

# Check for help flag
if [ "$1" = "-h" ] || [ "$1" = "--help" ] || [ "$1" = "help" ]; then
    show_usage
    exit 0
fi

# Get the project root directory (go up 3 levels from tests/ directory)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
DB_NAME="${1:-test_db}"
MODE="${2:-default}"

# Normalize mode
case "$MODE" in
    "detailed"|"report"|"full")
        MODE="detailed"
        ;;
    "simple"|"default"|"")
        MODE="simple"
        ;;
    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        show_usage
        exit 1
        ;;
esac

echo -e "${GREEN}=== SOR Contact Roles Test Runner ===${NC}\n"
echo -e "${BLUE}Mode:${NC} $MODE"
echo -e "${BLUE}Database:${NC} $DB_NAME"
echo ""

# Check if virtual environment exists
if [ ! -d "env312" ]; then
    echo -e "${RED}Error: Virtual environment 'env312' not found!${NC}"
    echo "Please create it first: python3.12 -m venv env312"
    exit 1
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source env312/bin/activate

# Check Python version
PYTHON_VERSION=$(python3 --version)
echo "Python version: $PYTHON_VERSION"

# Install/upgrade required packages if needed
echo -e "${YELLOW}Checking dependencies...${NC}"
if ! python3 -c "import babel" 2>/dev/null; then
    echo "Installing missing dependencies..."
    pip install --quiet -r requirements.txt 2>&1 | grep -v "already satisfied" || true
else
    echo -e "${GREEN}Dependencies OK${NC}"
fi

# Check if database exists, create if not
echo -e "${YELLOW}Using database: $DB_NAME${NC}"

# Check if database exists
DB_EXISTS=$(psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "$DB_NAME" && echo "yes" || echo "no")
if [ "$DB_EXISTS" = "yes" ]; then
    echo -e "${GREEN}Database '$DB_NAME' already exists.${NC}"
else
    echo -e "${YELLOW}Database '$DB_NAME' does not exist. Creating...${NC}"
    createdb "$DB_NAME" 2>&1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Database created successfully.${NC}"
    else
        echo -e "${YELLOW}Note: Database might already exist (this is OK)${NC}"
    fi
fi

# Install/upgrade module if needed
echo -e "${YELLOW}Installing/upgrading sor_contact_roles module...${NC}"
python3 odoo-bin --addons-path=addons,odoo/addons -d "$DB_NAME" \
    -i base,sor_contact_roles --stop-after-init \
    --log-level=warn 2>&1 | grep -E "(ERROR|WARNING|Installed|Upgraded|already installed)" || true

# Run tests based on mode
if [ "$MODE" = "detailed" ]; then
    echo -e "\n${GREEN}Running tests with detailed report...${NC}\n"
    # Use run_tests_with_report.sh which uses tee to properly capture output
    ./addons/sor_contact_roles/tests/run_tests_with_report.sh "$DB_NAME" 8070
    EXIT_CODE=$?
else
    echo -e "\n${GREEN}Running tests...${NC}\n"
    python3 odoo-bin --addons-path=addons,odoo/addons -d "$DB_NAME" \
        --http-port=8070 --test-enable --stop-after-init \
        --test-tags=sor_contact_roles \
        --log-level=test
    EXIT_CODE=$?
fi

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}=== Tests Complete ===${NC}"
else
    echo -e "\n${RED}=== Tests Failed ===${NC}"
fi

exit $EXIT_CODE

