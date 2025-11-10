#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pty_basic.py - Basic PTY functionality test

Tests basic PTY operations without requiring a J-Link connection.
This validates that PTY creation and I/O work correctly on the system.
"""

import os
import sys
import pty
import time
import select
import errno


def test_pty_creation():
    """Test PTY creation."""
    print("Testing PTY creation...")
    try:
        master_fd, slave_fd = pty.openpty()
        if master_fd < 0 or slave_fd < 0:
            print("FAILED: Invalid file descriptors")
            return False
        
        pty_name = os.ttyname(slave_fd)
        if not pty_name:
            print("FAILED: Could not get PTY name")
            os.close(master_fd)
            os.close(slave_fd)
            return False
        
        print(f"PASSED: Created PTY {pty_name}")
        os.close(master_fd)
        os.close(slave_fd)
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_pty_read_write():
    """Test PTY read/write."""
    print("\nTesting PTY read/write...")
    try:
        master_fd, slave_fd = pty.openpty()
        pty_name = os.ttyname(slave_fd)
        
        # Test data
        test_data = b"Hello, PTY!\n"
        
        # Write to master
        written = os.write(master_fd, test_data)
        if written != len(test_data):
            print(f"FAILED: Partial write {written}/{len(test_data)}")
            os.close(master_fd)
            os.close(slave_fd)
            return False
        
        # Read from slave
        time.sleep(0.1)  # Small delay
        ready, _, _ = select.select([slave_fd], [], [], 1.0)
        if not ready:
            print("FAILED: No data available for reading")
            os.close(master_fd)
            os.close(slave_fd)
            return False
        
        data = os.read(slave_fd, len(test_data) + 100)
        if data != test_data:
            print(f"FAILED: Data mismatch")
            print(f"  Expected: {test_data}")
            print(f"  Got: {data}")
            os.close(master_fd)
            os.close(slave_fd)
            return False
        
        print("PASSED: Read/write test successful")
        os.close(master_fd)
        os.close(slave_fd)
        return True
        
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pty_nonblocking():
    """Test non-blocking PTY operations."""
    print("\nTesting non-blocking PTY operations...")
    try:
        master_fd, slave_fd = pty.openpty()
        
        # Set non-blocking
        import fcntl
        flags = fcntl.fcntl(slave_fd, fcntl.F_GETFL)
        fcntl.fcntl(slave_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        
        # Try to read (should return EAGAIN)
        try:
            data = os.read(slave_fd, 1024)
            print("FAILED: Non-blocking read should have raised EAGAIN")
            os.close(master_fd)
            os.close(slave_fd)
            return False
        except OSError as e:
            if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
                print(f"FAILED: Unexpected error: {e}")
                os.close(master_fd)
                os.close(slave_fd)
                return False
        
        print("PASSED: Non-blocking operations work correctly")
        os.close(master_fd)
        os.close(slave_fd)
        return True
        
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all basic PTY tests."""
    print("=" * 60)
    print("Basic PTY Functionality Tests")
    print("=" * 60)
    
    tests = [
        test_pty_creation,
        test_pty_read_write,
        test_pty_nonblocking,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"Test raised exception: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

