#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_tests.py - Test runner for rtt2pty_pylink

Runs all available tests and provides a summary.
"""

import os
import sys
import subprocess
import argparse


def run_test(test_script, description, requires_hardware=False):
    """Run a test script.
    
    Args:
        test_script: Path to test script
        description: Description of the test
        requires_hardware: Whether test requires hardware
        
    Returns:
        tuple: (success, output)
    """
    if not os.path.exists(test_script):
        return False, f"Test script not found: {test_script}"
    
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"{'=' * 60}")
    
    try:
        result = subprocess.run(
            [sys.executable, test_script],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        return result.returncode == 0, result.stdout + result.stderr
        
    except subprocess.TimeoutExpired:
        return False, "Test timed out"
    except Exception as e:
        return False, f"Error running test: {e}"


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Run tests for rtt2pty_pylink',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--skip-hardware', action='store_true',
                       help='Skip tests that require hardware')
    parser.add_argument('--basic-only', action='store_true',
                       help='Run only basic PTY tests (no hardware required)')
    
    args = parser.parse_args()
    
    test_dir = os.path.dirname(os.path.abspath(__file__))
    
    tests = [
        {
            'script': os.path.join(test_dir, 'test_pty_basic.py'),
            'description': 'Basic PTY Functionality Tests',
            'requires_hardware': False
        },
        {
            'script': os.path.join(test_dir, 'test_integration.py'),
            'description': 'Integration Test (requires J-Link)',
            'requires_hardware': True
        },
    ]
    
    if args.basic_only:
        tests = [t for t in tests if not t['requires_hardware']]
    
    results = []
    
    for test in tests:
        if args.skip_hardware and test['requires_hardware']:
            print(f"\nSkipping {test['description']} (requires hardware)")
            continue
        
        success, output = run_test(
            test['script'],
            test['description'],
            test['requires_hardware']
        )
        
        results.append({
            'name': test['description'],
            'success': success,
            'output': output
        })
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for r in results if r['success'])
    failed = len(results) - passed
    
    for result in results:
        status = "PASSED" if result['success'] else "FAILED"
        print(f"{status}: {result['name']}")
    
    print(f"\nTotal: {len(results)} tests, {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

