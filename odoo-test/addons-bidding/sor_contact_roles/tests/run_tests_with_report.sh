#!/bin/bash
# Enhanced test runner with detailed reporting

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get the project root directory
# This script is in addons/sor_contact_roles/tests, so go up 3 levels
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  SOR Contact Roles - Test Report${NC}"
echo -e "${CYAN}========================================${NC}\n"

# Activate virtual environment
if [ -d "env312" ]; then
    source env312/bin/activate
    echo -e "${GREEN}✓${NC} Virtual environment activated"
else
    echo -e "${RED}✗${NC} Virtual environment 'env312' not found!"
    exit 1
fi

# Database name
DB_NAME="${1:-test_db}"
HTTP_PORT="${2:-8070}"

# Find available port if specified port is in use
if lsof -ti:$HTTP_PORT > /dev/null 2>&1; then
    echo -e "${YELLOW}Port $HTTP_PORT in use, finding available port...${NC}"
    HTTP_PORT=8070
    while lsof -ti:$HTTP_PORT > /dev/null 2>&1; do
        HTTP_PORT=$((HTTP_PORT + 1))
        if [ $HTTP_PORT -gt 8099 ]; then
            echo -e "${RED}Error: Could not find available port${NC}"
            exit 1
        fi
    done
    echo -e "${YELLOW}Using port $HTTP_PORT${NC}"
fi

echo -e "${BLUE}Database:${NC} $DB_NAME"
echo -e "${BLUE}Port:${NC} $HTTP_PORT\n"

# Create temporary file for test output
TEMP_OUTPUT=$(mktemp)
TEMP_ERROR=$(mktemp)

echo -e "${YELLOW}Running tests...${NC}\n"
echo -e "${CYAN}----------------------------------------${NC}"

# Run tests and capture output to temp file first
python3 odoo-bin --addons-path=addons,odoo/addons -d "$DB_NAME" \
    --http-port="$HTTP_PORT" --test-enable --stop-after-init \
    --test-tags=sor_contact_roles --log-level=test \
    2>&1 | tee "$TEMP_OUTPUT"

# Now parse the captured output
echo ""
while IFS= read -r line; do
    # Parse and format test output
    if [[ $line =~ "Starting" ]] && [[ $line =~ "test_" ]]; then
        test_name=$(echo "$line" | sed -n 's/.*Starting \(.*\)\.\.\..*/\1/p')
        echo -e "${BLUE}▶${NC} Running: ${CYAN}$test_name${NC}"
    elif [[ $line =~ "FAIL:" ]]; then
        echo -e "${RED}✗ FAIL${NC}: $line"
    elif [[ $line =~ "ERROR:" ]]; then
        echo -e "${RED}✗ ERROR${NC}: $line"
    elif [[ $line =~ "skipped" ]]; then
        echo -e "${YELLOW}⊘ SKIP${NC}: $line"
    fi
done < "$TEMP_OUTPUT"

# Extract summary information
echo -e "\n${CYAN}----------------------------------------${NC}"
echo -e "${CYAN}Test Summary${NC}"
echo -e "${CYAN}----------------------------------------${NC}\n"

# Extract module count
MODULE_LINES=$(grep "modules loaded" "$TEMP_OUTPUT" | grep -oE "[0-9]+ modules loaded" | head -1 | grep -oE "[0-9]+" || echo "0")
echo -e "${BLUE}Modules Loaded:${NC} $MODULE_LINES"

# Extract test statistics
if grep -q "tests.stats" "$TEMP_OUTPUT"; then
    STATS_LINE=$(grep "tests.stats" "$TEMP_OUTPUT" | tail -1)
    TOTAL_TESTS=$(echo "$STATS_LINE" | sed -n 's/.*: \([0-9]*\) tests.*/\1/p')
    EXECUTION_TIME=$(echo "$STATS_LINE" | sed -n 's/.*tests \([0-9.]*\)s.*/\1/p')
    QUERIES=$(echo "$STATS_LINE" | sed -n 's/.* \([0-9]*\) queries.*/\1/p')
    
    echo -e "${BLUE}Total Tests:${NC} $TOTAL_TESTS"
    echo -e "${BLUE}Execution Time:${NC} ${EXECUTION_TIME}s"
    echo -e "${BLUE}Database Queries:${NC} $QUERIES"
fi

# Extract pass/fail count
RESULT_LINE=$(grep "tests.result" "$TEMP_OUTPUT" | tail -1)
FAILED=$(echo "$RESULT_LINE" | sed -n 's/.*\([0-9]*\) failed.*/\1/p')
ERRORS=$(echo "$RESULT_LINE" | sed -n 's/.*\([0-9]*\) error.*/\1/p')
TOTAL_RUN=$(echo "$RESULT_LINE" | sed -n 's/.*of \([0-9]*\) tests.*/\1/p')

echo -e "\n${CYAN}Test Results:${NC}"
if [ -z "$FAILED" ] || [ "$FAILED" = "0" ]; then
    FAILED=0
fi
if [ -z "$ERRORS" ] || [ "$ERRORS" = "0" ]; then
    ERRORS=0
fi

PASSED=$((TOTAL_RUN - FAILED - ERRORS))

echo -e "  ${GREEN}✓ Passed:${NC} $PASSED"
if [ "$FAILED" -gt 0 ]; then
    echo -e "  ${RED}✗ Failed:${NC} $FAILED"
fi
if [ "$ERRORS" -gt 0 ]; then
    echo -e "  ${RED}✗ Errors:${NC} $ERRORS"
fi
echo -e "  ${BLUE}Total:${NC} $TOTAL_RUN"

# Extract test file breakdown
echo -e "\n${CYAN}Test Files:${NC}"
grep -E "Starting.*test_" "$TEMP_OUTPUT" | \
    sed 's/.*Starting \(.*\)\.\.\..*/\1/' | \
    sed 's/\.test_/ - /' | \
    sort -u | while read -r test; do
    echo -e "  ${GREEN}✓${NC} $test"
done

# Show failures if any
if [ "$FAILED" -gt 0 ] || [ "$ERRORS" -gt 0 ]; then
    echo -e "\n${RED}----------------------------------------${NC}"
    echo -e "${RED}Failures & Errors${NC}"
    echo -e "${RED}----------------------------------------${NC}\n"
    grep -A 10 -E "(FAIL:|ERROR:)" "$TEMP_OUTPUT" || true
fi

# Final status
echo -e "\n${CYAN}----------------------------------------${NC}"
if [ "$FAILED" -eq 0 ] && [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    EXIT_CODE=0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    EXIT_CODE=1
fi
echo -e "${CYAN}----------------------------------------${NC}\n"

# Cleanup
rm -f "$TEMP_OUTPUT" "$TEMP_ERROR"

exit $EXIT_CODE
