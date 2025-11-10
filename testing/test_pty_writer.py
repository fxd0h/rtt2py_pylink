#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pty_writer.py - Test script to write to PTY created by rtt2pty_pylink

This script connects to a PTY and writes data to it, which will be sent
to the RTT DOWN buffer (for bidirectional mode).
"""

import os
import sys
import time
import argparse
import errno


def write_to_pty(pty_path, data, delay=0.1):
    """Write data to PTY.
    
    Args:
        pty_path: Path to the PTY device
        data: Data to write (bytes or string)
        delay: Delay between writes (seconds)
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not os.path.exists(pty_path):
        print(f"Error: PTY path does not exist: {pty_path}", file=sys.stderr)
        return False
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    if not isinstance(data, bytes):
        print("Error: Data must be bytes or string", file=sys.stderr)
        return False
    
    try:
        fd = os.open(pty_path, os.O_WRONLY)
    except OSError as e:
        print(f"Error: Failed to open PTY '{pty_path}': {e}", file=sys.stderr)
        return False
    
    try:
        print(f"Writing to PTY: {pty_path}")
        
        total_written = 0
        for i in range(0, len(data), 1024):
            chunk = data[i:i+1024]
            try:
                written = os.write(fd, chunk)
                total_written += written
                if written != len(chunk):
                    print(f"Warning: Partial write: {written}/{len(chunk)} bytes", file=sys.stderr)
                if delay > 0:
                    time.sleep(delay)
            except OSError as e:
                if e.errno == errno.EIO:
                    print(f"Error: I/O error on PTY: {e}", file=sys.stderr)
                    return False
                raise
        
        print(f"Successfully wrote {total_written} bytes", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"Error writing to PTY: {e}", file=sys.stderr)
        return False
    finally:
        os.close(fd)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Write data to PTY created by rtt2pty_pylink',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Write a string
  %(prog)s /dev/pts/5 "Hello RTT"
  
  # Write from stdin
  echo "Test" | %(prog)s /dev/pts/5 -
  
  # Write with delay between chunks
  %(prog)s /dev/pts/5 "Hello" -d 0.5
        """
    )
    parser.add_argument('pty_path', help='Path to PTY device (e.g., /dev/pts/5)')
    parser.add_argument('data', nargs='?', default='-',
                       help='Data to write (use "-" for stdin, default: "-")')
    parser.add_argument('-d', '--delay', type=float, default=0.1,
                       help='Delay between writes in seconds (default: 0.1)')
    
    args = parser.parse_args()
    
    if not args.pty_path:
        print("Error: PTY path is required", file=sys.stderr)
        return 1
    
    # Read data
    if args.data == '-':
        print("Reading from stdin...", file=sys.stderr)
        data = sys.stdin.buffer.read()
    else:
        data = args.data
    
    if not data:
        print("Error: No data to write", file=sys.stderr)
        return 1
    
    success = write_to_pty(args.pty_path, data, args.delay)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

