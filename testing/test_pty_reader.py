#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pty_reader.py - Test script to read from PTY created by rtt2pty_pylink

This script connects to a PTY and reads RTT data from it, demonstrating
that the rtt2pty_pylink bridge works correctly.
"""

import os
import sys
import select
import time
import argparse
import errno


def read_from_pty(pty_path, timeout=30, max_bytes=None):
    """Read data from PTY.
    
    Args:
        pty_path: Path to the PTY device
        timeout: Maximum time to wait for data (seconds)
        max_bytes: Maximum bytes to read (None for unlimited)
        
    Returns:
        bytes: Data read from PTY
    """
    if not os.path.exists(pty_path):
        print(f"Error: PTY path does not exist: {pty_path}", file=sys.stderr)
        return None
    
    if not os.path.ischar(pty_path) and not os.path.exists(pty_path):
        print(f"Error: Path is not a character device: {pty_path}", file=sys.stderr)
        return None
    
    try:
        fd = os.open(pty_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        print(f"Error: Failed to open PTY '{pty_path}': {e}", file=sys.stderr)
        return None
    
    data = bytearray()
    start_time = time.time()
    
    try:
        print(f"Reading from PTY: {pty_path}")
        print("Press Ctrl+C to stop...")
        
        while True:
            if timeout > 0 and (time.time() - start_time) > timeout:
                print(f"\nTimeout after {timeout} seconds", file=sys.stderr)
                break
            
            if max_bytes and len(data) >= max_bytes:
                print(f"\nRead {len(data)} bytes (limit reached)", file=sys.stderr)
                break
            
            try:
                ready, _, _ = select.select([fd], [], [], 1.0)
                if ready:
                    chunk = os.read(fd, 4096)
                    if chunk:
                        data.extend(chunk)
                        # Write to stdout immediately
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                    else:
                        # EOF
                        print("\nEOF reached", file=sys.stderr)
                        break
            except select.error as e:
                if e.args[0] == errno.EBADF:
                    print("\nError: File descriptor invalid", file=sys.stderr)
                    break
                raise
            except OSError as e:
                if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                    # No data available, continue
                    continue
                elif e.errno == errno.EIO:
                    print("\nI/O error on PTY", file=sys.stderr)
                    break
                raise
    
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
    finally:
        os.close(fd)
    
    return bytes(data)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Read RTT data from PTY created by rtt2pty_pylink',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Read from PTY with 30 second timeout
  %(prog)s /dev/pts/5
  
  # Read with custom timeout
  %(prog)s /dev/pts/5 -t 60
  
  # Read maximum 1024 bytes
  %(prog)s /dev/pts/5 -m 1024
        """
    )
    parser.add_argument('pty_path', help='Path to PTY device (e.g., /dev/pts/5)')
    parser.add_argument('-t', '--timeout', type=int, default=30,
                       help='Timeout in seconds (default: 30, 0 for no timeout)')
    parser.add_argument('-m', '--max-bytes', type=int, default=None,
                       help='Maximum bytes to read (default: unlimited)')
    
    args = parser.parse_args()
    
    if not args.pty_path:
        print("Error: PTY path is required", file=sys.stderr)
        return 1
    
    data = read_from_pty(args.pty_path, args.timeout, args.max_bytes)
    
    if data is None:
        return 1
    
    print(f"\n\nTotal bytes read: {len(data)}", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())

