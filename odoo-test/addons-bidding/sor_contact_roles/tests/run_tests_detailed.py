#!/usr/bin/env python3  # ruff: noqa
"""
Enhanced test runner with detailed reporting for SOR Contact Roles module.
Shows: modules loaded, test cases, outputs, and pass/fail status.
"""

import re
import subprocess
import sys
from collections import defaultdict


# Colors for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


def print_header(text):
    print(f"\n{Colors.CYAN}{'=' * 60}{Colors.NC}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text:^60}{Colors.NC}")
    print(f"{Colors.CYAN}{'=' * 60}{Colors.NC}\n")


def print_section(text):
    print(f"\n{Colors.BLUE}{'-' * 60}{Colors.NC}")
    print(f"{Colors.BLUE}{text}{Colors.NC}")
    print(f"{Colors.BLUE}{'-' * 60}{Colors.NC}\n")


def run_tests(database='test_db', port=8070):
    """Run tests and parse output for detailed reporting."""

    print_header("SOR Contact Roles - Detailed Test Report")

    # Build command
    cmd = [
        'python3', 'odoo-bin',
        '--addons-path', 'addons,odoo/addons',
        '-d', database,
        '--http-port', str(port),
        '--test-enable',
        '--stop-after-init',
        '--test-tags', 'sor_contact_roles',
        '--log-level', 'test',
    ]

    print(f"{Colors.YELLOW}Running command:{Colors.NC}")
    print(f"  {' '.join(cmd)}\n")
    print(f"{Colors.YELLOW}Database:{Colors.NC} {database}")
    print(f"{Colors.YELLOW}Port:{Colors.NC} {port}\n")

    # Track test information
    modules_loaded = []
    test_cases = []
    test_results = defaultdict(list)
    failures = []
    errors = []
    skipped = []

    # Statistics
    stats = {
        'total_tests': 0,
        'execution_time': 0,
        'queries': 0,
        'failed': 0,
        'errors': 0,
        'passed': 0,
    }

    print_section("Test Execution")

    # Run tests and parse output line by line
    # Use Popen and read output as it comes
    import os
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,  # Line buffered
        encoding='utf-8',
        errors='replace',
        env=env,
    )

    current_test = None
    current_class = None

    # Read output line by line as it comes
    output_lines = []
    try:
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            output_lines.append(line.rstrip())
    except Exception as e:
        print(f"{Colors.YELLOW}Warning: Error reading output: {e}{Colors.NC}")

    # Wait for process to complete and get exit code
    exit_code = process.wait()

    if not output_lines:
        print(f"{Colors.YELLOW}Warning: No output captured from test process (exit code: {exit_code}){Colors.NC}")

    for line in output_lines:
        line = line.rstrip()

        # Track modules loaded
        if 'modules loaded' in line:
            match = re.search(r'(\d+) modules loaded', line)
            if match:
                modules_loaded.append(int(match.group(1)))

        # Track test start - handle both formats: "Starting TestClass.test_method" and "INFO db Starting TestClass.test_method"
        if 'Starting' in line and 'test_' in line:
            # Try to match with INFO prefix first, then without
            match = re.search(r'Starting ([\w.]+)\.([\w_]+)', line)
            if match:
                current_class = match.group(1)
                current_test = match.group(2)
                test_name = f"{current_class}.{current_test}"
                test_cases.append(test_name)
                print(f"  {Colors.BLUE}▶{Colors.NC} {Colors.CYAN}{test_name}{Colors.NC}")
                if current_class not in test_results:
                    test_results[current_class] = []
                test_results[current_class].append({
                    'name': current_test,
                    'status': 'running',
                    'output': [],
                })

        # Track failures
        if 'FAIL:' in line:
            stats['failed'] += 1
            if current_test:
                for test in test_results[current_class]:
                    if test['name'] == current_test:
                        test['status'] = 'failed'
                        test['output'].append(line)
                failures.append(f"{current_class}.{current_test}")
                print(f"    {Colors.RED}✗ FAILED{Colors.NC}")

        # Track errors
        if 'ERROR:' in line:
            stats['errors'] += 1
            if current_test:
                for test in test_results[current_class]:
                    if test['name'] == current_test:
                        test['status'] = 'error'
                        test['output'].append(line)
                errors.append(f"{current_class}.{current_test}")
                print(f"    {Colors.RED}✗ ERROR{Colors.NC}")

        # Track skipped
        if 'skipped' in line.lower():
            if current_test:
                for test in test_results[current_class]:
                    if test['name'] == current_test:
                        test['status'] = 'skipped'
                skipped.append(f"{current_class}.{current_test}")
                print(f"    {Colors.YELLOW}⊘ SKIPPED{Colors.NC}")

        # Track test statistics - handle formats: "tests.stats:" or "odoo.tests.stats:"
        # Format: "INFO test_db_new odoo.tests.stats: sor_contact_roles: 135 tests 0.73s 2161 queries"
        if 'tests.stats' in line:
            # Match: "sor_contact_roles: 135 tests 0.73s 2161 queries" or "135 tests 0.73s 2161 queries"
            match = re.search(r':\s*.*?(\d+)\s+tests\s+([\d.]+)s\s+(\d+)\s+queries', line)
            if not match:
                match = re.search(r'(\d+)\s+tests\s+([\d.]+)s\s+(\d+)\s+queries', line)
            if match:
                stats['total_tests'] = int(match.group(1))
                stats['execution_time'] = float(match.group(2))
                stats['queries'] = int(match.group(3))

        # Track final results - handle formats: "tests.result:" or "odoo.tests.result:"
        # Format: "INFO test_db_new odoo.tests.result: 0 failed, 0 error(s) of 119 tests when loading database 'test_db_new'"
        if 'tests.result' in line:
            # Match: "0 failed, 0 error(s) of 119 tests"
            match = re.search(r'(\d+)\s+failed,\s+(\d+)\s+error', line)
            if match:
                stats['failed'] = int(match.group(1))
                stats['errors'] = int(match.group(2))
            match = re.search(r'of\s+(\d+)\s+tests', line)
            if match:
                total = int(match.group(1))
                stats['passed'] = total - stats['failed'] - stats['errors']

    # Exit code is available from process.wait()
    exit_code = process.returncode

    # Print detailed report
    print_section("Test Summary")

    # Modules loaded
    if modules_loaded:
        total_modules = sum(modules_loaded)
        print(f"{Colors.BLUE}Modules Loaded:{Colors.NC} {total_modules}")
        print(f"  - Initial load: {modules_loaded[0] if len(modules_loaded) > 0 else 0}")
        if len(modules_loaded) > 1:
            print(f"  - Full load: {modules_loaded[1]}")

    # Test statistics
    print(f"\n{Colors.BLUE}Test Statistics:{Colors.NC}")
    print(f"  Total Tests: {stats['total_tests']}")
    print(f"  Execution Time: {stats['execution_time']}s")
    print(f"  Database Queries: {stats['queries']}")

    # Test results
    print(f"\n{Colors.BLUE}Test Results:{Colors.NC}")
    print(f"  {Colors.GREEN}✓ Passed:{Colors.NC} {stats['passed']}")
    if stats['failed'] > 0:
        print(f"  {Colors.RED}✗ Failed:{Colors.NC} {stats['failed']}")
    if stats['errors'] > 0:
        print(f"  {Colors.RED}✗ Errors:{Colors.NC} {stats['errors']}")
    if skipped:
        print(f"  {Colors.YELLOW}⊘ Skipped:{Colors.NC} {len(skipped)}")

    # Test files breakdown
    print_section("Test Files Breakdown")
    for test_class, tests in sorted(test_results.items()):
        passed_count = sum(1 for t in tests if t['status'] == 'running' or t['status'] == 'passed')
        failed_count = sum(1 for t in tests if t['status'] == 'failed')
        error_count = sum(1 for t in tests if t['status'] == 'error')
        skipped_count = sum(1 for t in tests if t['status'] == 'skipped')
        total_count = len(tests)

        status_color = Colors.GREEN if failed_count == 0 and error_count == 0 else Colors.RED
        print(f"{status_color}✓{Colors.NC} {Colors.CYAN}{test_class}{Colors.NC}")
        print(f"    Tests: {total_count} | Passed: {passed_count} | Failed: {failed_count} | Errors: {error_count} | Skipped: {skipped_count}")

    # Detailed test cases
    print_section("Individual Test Cases")
    for test_class, tests in sorted(test_results.items()):
        print(f"\n{Colors.BOLD}{test_class}{Colors.NC}:")
        for test in tests:
            status_icon = Colors.GREEN + "✓" if test['status'] == 'running' or test['status'] == 'passed' else \
                         Colors.RED + "✗" if test['status'] == 'failed' or test['status'] == 'error' else \
                         Colors.YELLOW + "⊘"
            status_text = "PASS" if test['status'] == 'running' or test['status'] == 'passed' else \
                         "FAIL" if test['status'] == 'failed' else \
                         "ERROR" if test['status'] == 'error' else \
                         "SKIP"
            print(f"  {status_icon}{Colors.NC} {test['name']:50} [{status_text}]")
            if test['output']:
                for output_line in test['output'][:3]:  # Show first 3 lines of output
                    print(f"      {Colors.YELLOW}{output_line[:70]}{Colors.NC}")

    # Failures and errors details
    if failures or errors:
        print_section("Failures & Errors Details")
        for failure in failures:
            print(f"{Colors.RED}✗ {failure}{Colors.NC}")
        for error in errors:
            print(f"{Colors.RED}✗ {error}{Colors.NC}")

    # Final status
    print_section("Final Status")
    if stats['failed'] == 0 and stats['errors'] == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL TESTS PASSED!{Colors.NC}")
        return 0 if exit_code == 0 else exit_code
    print(f"{Colors.RED}{Colors.BOLD}✗ SOME TESTS FAILED{Colors.NC}")
    return 1


if __name__ == '__main__':
    database = sys.argv[1] if len(sys.argv) > 1 else 'test_db'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8070
    sys.exit(run_tests(database, port))
