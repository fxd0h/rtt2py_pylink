#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_integration.py - Integration test for rtt2pty_pylink

This script performs end-to-end testing of the rtt2pty_pylink bridge:
1. Starts rtt2pty_pylink in the background
2. Reads from the created PTY
3. Optionally writes to the PTY (if bidirectional)
4. Validates data flow
"""

import os
import sys
import time
import subprocess
import signal
import tempfile
import argparse
import errno


def find_pty_from_output(output_lines):
    """Extract PTY path from rtt2pty_pylink output.
    
    Args:
        output_lines: List of output lines from rtt2pty_pylink
        
    Returns:
        str: PTY path or None if not found
    """
    for line in output_lines:
        if 'PTY name is' in line:
            parts = line.split('PTY name is')
            if len(parts) > 1:
                return parts[1].strip()
    return None


def test_pty_read(pty_path, timeout=5):
    """Test reading from PTY.
    
    Args:
        pty_path: Path to PTY
        timeout: Timeout in seconds
        
    Returns:
        tuple: (success, data_read)
    """
    if not os.path.exists(pty_path):
        return False, None
    
    try:
        fd = os.open(pty_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        print(f"Error opening PTY: {e}", file=sys.stderr)
        return False, None
    
    data = bytearray()
    start_time = time.time()
    
    try:
        import select
        while (time.time() - start_time) < timeout:
            ready, _, _ = select.select([fd], [], [], 0.5)
            if ready:
                chunk = os.read(fd, 4096)
                if chunk:
                    data.extend(chunk)
                else:
                    break
            time.sleep(0.1)
    except Exception as e:
        print(f"Error reading from PTY: {e}", file=sys.stderr)
        os.close(fd)
        return False, None
    
    os.close(fd)
    return True, bytes(data)


def test_pty_write(pty_path, test_data):
    """Test writing to PTY.
    
    Args:
        pty_path: Path to PTY
        test_data: Data to write (bytes)
        
    Returns:
        bool: True if successful
    """
    if not os.path.exists(pty_path):
        return False
    
    try:
        fd = os.open(pty_path, os.O_WRONLY)
        written = os.write(fd, test_data)
        os.close(fd)
        return written == len(test_data)
    except OSError as e:
        print(f"Error writing to PTY: {e}", file=sys.stderr)
        return False


def run_integration_test(device, buffer_name='Terminal', bidir=False, 
                        rtt_address=None, timeout=10):
    """Run integration test.
    
    Args:
        device: Target device name
        buffer_name: RTT buffer name
        bidir: Enable bidirectional mode
        rtt_address: RTT address or search range
        timeout: Test timeout in seconds
        
    Returns:
        bool: True if test passed
    """
    print("=" * 60)
    print("Integration Test for rtt2pty_pylink")
    print("=" * 60)
    
    # Build command
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                               'rtt2pty_pylink.py')
    
    if not os.path.exists(script_path):
        print(f"Error: Script not found: {script_path}", file=sys.stderr)
        return False
    
    cmd = [sys.executable, script_path, '-d', device, '-b', buffer_name]
    
    if bidir:
        cmd.append('--bidir')
    
    if rtt_address:
        cmd.extend(['-a', rtt_address])
    
    # Create temporary symlink path
    with tempfile.NamedTemporaryFile(delete=False, prefix='rtt_test_') as tmp:
        symlink_path = tmp.name
    
    cmd.extend(['-l', symlink_path])
    
    print(f"\nStarting rtt2pty_pylink...")
    print(f"Command: {' '.join(cmd)}")
    
    # Start rtt2pty_pylink
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
    except Exception as e:
        print(f"Error starting rtt2pty_pylink: {e}", file=sys.stderr)
        return False
    
    pty_path = None
    output_lines = []
    
    # Wait for PTY to be created
    print("Waiting for PTY creation...")
    start_time = time.time()
    
    while (time.time() - start_time) < timeout:
        if process.poll() is not None:
            # Process exited
            stdout, stderr = process.communicate()
            print(f"Process exited with code {process.returncode}", file=sys.stderr)
            print("STDOUT:", stdout, file=sys.stderr)
            print("STDERR:", stderr, file=sys.stderr)
            return False
        
        # Read output
        if process.stdout:
            line = process.stdout.readline()
            if line:
                output_lines.append(line.strip())
                print(f"Output: {line.strip()}")
                
                # Check for PTY name
                if 'PTY name is' in line:
                    pty_path = find_pty_from_output([line])
                    if pty_path:
                        print(f"Found PTY: {pty_path}")
                        break
        
        # Check symlink
        if os.path.exists(symlink_path) and os.path.islink(symlink_path):
            pty_path = os.readlink(symlink_path)
            print(f"Found PTY via symlink: {pty_path}")
            break
        
        time.sleep(0.1)
    
    if not pty_path:
        print("Error: PTY not created within timeout", file=sys.stderr)
        process.terminate()
        time.sleep(1)
        if process.poll() is None:
            process.kill()
        return False
    
    # Verify PTY exists
    if not os.path.exists(pty_path):
        print(f"Error: PTY path does not exist: {pty_path}", file=sys.stderr)
        process.terminate()
        time.sleep(1)
        if process.poll() is None:
            process.kill()
        return False
    
    print(f"\nPTY created successfully: {pty_path}")
    
    # Test reading from PTY
    print("\nTesting PTY read...")
    time.sleep(1)  # Give RTT time to initialize
    
    success, data = test_pty_read(pty_path, timeout=5)
    if success:
        print(f"Read test: PASSED ({len(data)} bytes read)")
        if data:
            print(f"Sample data (first 100 bytes): {data[:100]}")
    else:
        print("Read test: FAILED")
        process.terminate()
        time.sleep(1)
        if process.poll() is None:
            process.kill()
        return False
    
    # Test writing to PTY (if bidirectional)
    if bidir:
        print("\nTesting PTY write (bidirectional mode)...")
        test_data = b"TEST_DATA_FROM_PTY\n"
        success = test_pty_write(pty_path, test_data)
        if success:
            print("Write test: PASSED")
        else:
            print("Write test: FAILED")
            process.terminate()
            time.sleep(1)
            if process.poll() is None:
                process.kill()
            return False
    
    # Cleanup
    print("\nCleaning up...")
    process.terminate()
    time.sleep(1)
    if process.poll() is None:
        process.kill()
    
    # Remove symlink
    if os.path.exists(symlink_path):
        try:
            os.remove(symlink_path)
        except OSError:
            pass
    
    print("\n" + "=" * 60)
    print("Integration test: PASSED")
    print("=" * 60)
    return True


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Integration test for rtt2pty_pylink',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-d', '--device', default='NRF54L15_M33',
                       help='Target device name (default: NRF54L15_M33)')
    parser.add_argument('-b', '--buffer', default='Terminal',
                       help='RTT buffer name (default: Terminal)')
    parser.add_argument('-2', '--bidir', action='store_true',
                       help='Test bidirectional mode')
    parser.add_argument('-a', '--address',
                       help='RTT address or search range')
    parser.add_argument('-t', '--timeout', type=int, default=10,
                       help='Test timeout in seconds (default: 10)')
    
    args = parser.parse_args()
    
    success = run_integration_test(
        args.device,
        args.buffer,
        args.bidir,
        args.address,
        args.timeout
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

