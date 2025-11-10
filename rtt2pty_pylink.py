#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rtt2pty_pylink.py - RTT to PTY bridge using pylink

Functionally equivalent to rtt2pty but using pylink instead of direct dlopen.

This script demonstrates that it is possible to completely replicate rtt2pty
functionality using pylink without needing to modify the library.

References:
- Original rtt2pty: https://github.com/codecoup/tools-rtt2pty
"""

import pylink
import pty
import os
import select
import signal
import sys
import time
import argparse
import errno


class RTTBridgeError(Exception):
    """Custom exception for RTT bridge errors."""
    pass


def validate_speed(speed):
    """Validate SWD/JTAG speed value.
    
    Args:
        speed: Speed value in kHz
        
    Returns:
        int: Validated speed value
        
    Raises:
        ValueError: If speed is out of valid range
    """
    if speed < 5:
        raise ValueError(f"Speed too low: {speed} kHz (minimum: 5 kHz)")
    if speed > 50000:
        raise ValueError(f"Speed too high: {speed} kHz (maximum: 50000 kHz)")
    return speed


def parse_address(address_str):
    """Parse RTT address or search range string.
    
    Args:
        address_str: Address string (hex) or search range (start,size)
        
    Returns:
        tuple: (address, None) for specific address or (start, size) for range
        
    Raises:
        ValueError: If address format is invalid
    """
    if not address_str or not address_str.strip():
        raise ValueError("Empty address string")
    
    address_str = address_str.strip()
    
    if ',' in address_str:
        # Search range: "start,size"
        parts = address_str.split(',')
        if len(parts) != 2:
            raise ValueError(f"Invalid search range format: '{address_str}' (expected 'start,size')")
        
        start_str = parts[0].strip()
        size_str = parts[1].strip()
        
        if not start_str or not size_str:
            raise ValueError(f"Invalid search range format: '{address_str}' (both start and size required)")
        
        try:
            start = int(start_str, 16) if start_str.startswith('0x') else int(start_str, 16) if start_str.startswith('0X') else int(start_str)
            size = int(size_str, 16) if size_str.startswith('0x') else int(size_str, 16) if size_str.startswith('0X') else int(size_str)
        except ValueError as e:
            raise ValueError(f"Invalid number format in search range '{address_str}': {e}")
        
        if start < 0:
            raise ValueError(f"Invalid start address: 0x{start:X} (must be >= 0)")
        if size <= 0:
            raise ValueError(f"Invalid size: 0x{size:X} (must be > 0)")
        if size > 0xFFFFFFFF:
            raise ValueError(f"Size too large: 0x{size:X} (maximum: 0xFFFFFFFF)")
        
        return (start, size)
    else:
        # Specific address
        try:
            addr = int(address_str, 16) if address_str.startswith(('0x', '0X')) else int(address_str)
        except ValueError as e:
            raise ValueError(f"Invalid address format '{address_str}': {e}")
        
        if addr < 0:
            raise ValueError(f"Invalid address: 0x{addr:X} (must be >= 0)")
        if addr > 0xFFFFFFFFFFFFFFFF:
            raise ValueError(f"Address too large: 0x{addr:X}")
        
        return (addr, None)


def find_buffer_by_name(jlink, name, up=True, max_retries=3):
    """Find an RTT buffer by name with retry logic.
    
    Args:
        jlink: pylink.JLink instance
        name: Buffer name to search for
        up: True for UP buffers, False for DOWN buffers
        max_retries: Maximum number of retries if RTT not ready
        
    Returns:
        tuple: (buffer index, descriptor) or (-1, None) if not found
        
    Raises:
        RTTBridgeError: If RTT is not active or other critical error
    """
    if not name or not name.strip():
        return -1, None
    
    name = name.strip()
    
    for attempt in range(max_retries):
        try:
            # Verify RTT is active
            if not is_rtt_active(jlink):
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                raise RTTBridgeError("RTT is not active. Ensure RTT has been started successfully.")
            
            num_buffers = (jlink.rtt_get_num_up_buffers() if up 
                          else jlink.rtt_get_num_down_buffers())
            
            if num_buffers == 0:
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                direction = "UP" if up else "DOWN"
                raise RTTBridgeError(f"No {direction} buffers available")
            
            for index in range(num_buffers):
                try:
                    desc = jlink.rtt_get_buf_descriptor(index, up)
                    if desc is None:
                        continue
                    
                    buffer_name = desc.name.rstrip('\x00') if isinstance(desc.name, str) else desc.name.decode('utf-8', errors='replace').rstrip('\x00')
                    if buffer_name == name:
                        # Validate descriptor
                        if desc.SizeOfBuffer == 0:
                            raise RTTBridgeError(f"Buffer '{name}' has invalid size (0)")
                        return index, desc
                except (pylink.errors.JLinkRTTException, UnicodeDecodeError) as e:
                    # Skip this buffer and continue searching
                    continue
            
            # Buffer not found
            return -1, None
            
        except pylink.errors.JLinkRTTException as e:
            if attempt < max_retries - 1:
                time.sleep(0.2)
                continue
            raise RTTBridgeError(f"Failed to query RTT buffers: {e}")
        except Exception as e:
            raise RTTBridgeError(f"Unexpected error while searching for buffer '{name}': {e}")
    
    return -1, None


def print_buffers(jlink):
    """Print the list of available RTT buffers.
    
    Args:
        jlink: pylink.JLink instance
        
    Returns:
        bool: True if buffers were printed successfully, False otherwise
    """
    try:
        if not is_rtt_active(jlink):
            print("Error: RTT is not active", file=sys.stderr)
            return False
        
        print("Up-buffers:")
        try:
            num_up = jlink.rtt_get_num_up_buffers()
            if num_up == 0:
                print("  (none)")
            else:
                for i in range(num_up):
                    try:
                        desc = jlink.rtt_get_buf_descriptor(i, True)
                        if desc:
                            name = desc.name.rstrip('\x00') if isinstance(desc.name, str) else desc.name.decode('utf-8', errors='replace').rstrip('\x00')
                            print(f"  #{i} {name} (size={desc.SizeOfBuffer})")
                    except (pylink.errors.JLinkRTTException, UnicodeDecodeError, AttributeError) as e:
                        print(f"  #{i} (error reading descriptor: {e})")
        except pylink.errors.JLinkRTTException as e:
            print(f"  Error reading up-buffers: {e}", file=sys.stderr)
            return False
        
        print("Down-buffers:")
        try:
            num_down = jlink.rtt_get_num_down_buffers()
            if num_down == 0:
                print("  (none)")
            else:
                for i in range(num_down):
                    try:
                        desc = jlink.rtt_get_buf_descriptor(i, False)
                        if desc:
                            name = desc.name.rstrip('\x00') if isinstance(desc.name, str) else desc.name.decode('utf-8', errors='replace').rstrip('\x00')
                            print(f"  #{i} {name} (size={desc.SizeOfBuffer})")
                    except (pylink.errors.JLinkRTTException, UnicodeDecodeError, AttributeError) as e:
                        print(f"  #{i} (error reading descriptor: {e})")
        except pylink.errors.JLinkRTTException as e:
            print(f"  Error reading down-buffers: {e}", file=sys.stderr)
            return False
        
        return True
        
    except Exception as e:
        print(f"Error printing buffers: {e}", file=sys.stderr)
        return False


def verify_jlink_connection(jlink):
    """Verify J-Link connection is valid and device is connected.
    
    Args:
        jlink: pylink.JLink instance
        
    Raises:
        RTTBridgeError: If connection is invalid
    """
    try:
        if not jlink.opened():
            raise RTTBridgeError("J-Link DLL is not open")
        
        if not jlink.connected():
            raise RTTBridgeError("J-Link is not connected to target device")
        
        if not jlink.target_connected():
            raise RTTBridgeError("Target device is not connected")
        
        # Try to get device info to verify connection
        try:
            _ = jlink.product_name
            _ = jlink.serial_number
        except Exception as e:
            raise RTTBridgeError(f"Failed to get J-Link device information: {e}")
            
    except pylink.errors.JLinkException as e:
        raise RTTBridgeError(f"J-Link connection error: {e}")


def is_rtt_active(jlink):
    """Check if RTT is active by attempting to get buffer count.
    
    Args:
        jlink: pylink.JLink instance
        
    Returns:
        bool: True if RTT is active, False otherwise
    """
    try:
        # Try to use rtt_is_active if available
        if hasattr(jlink, 'rtt_is_active'):
            return jlink.rtt_is_active()
        # Fallback: try to get buffer count
        num_buffers = jlink.rtt_get_num_up_buffers()
        return num_buffers > 0
    except (pylink.errors.JLinkRTTException, AttributeError):
        return False
    except Exception:
        return False


def create_pty():
    """Create a pseudo-terminal pair.
    
    Returns:
        tuple: (master_fd, slave_fd, pty_name)
        
    Raises:
        RTTBridgeError: If PTY creation fails
    """
    try:
        master_fd, slave_fd = pty.openpty()
        
        if master_fd < 0 or slave_fd < 0:
            raise RTTBridgeError("Failed to create PTY: invalid file descriptors")
        
        try:
            pty_name = os.ttyname(slave_fd)
            if not pty_name:
                raise RTTBridgeError("Failed to get PTY name")
        except OSError as e:
            os.close(master_fd)
            os.close(slave_fd)
            raise RTTBridgeError(f"Failed to get PTY name: {e}")
        
        return master_fd, slave_fd, pty_name
        
    except OSError as e:
        raise RTTBridgeError(f"Failed to create PTY: {e}")


def create_symlink(target, link_path):
    """Create a symlink to the PTY.
    
    Args:
        target: Target path (PTY name)
        link_path: Symlink path to create
        
    Raises:
        RTTBridgeError: If symlink creation fails
    """
    try:
        # Remove existing symlink or file if it exists
        if os.path.exists(link_path):
            if os.path.islink(link_path):
                os.remove(link_path)
            else:
                raise RTTBridgeError(f"Path exists and is not a symlink: {link_path}")
        
        # Create parent directory if needed
        link_dir = os.path.dirname(link_path)
        if link_dir and not os.path.exists(link_dir):
            try:
                os.makedirs(link_dir, mode=0o755, exist_ok=True)
            except OSError as e:
                raise RTTBridgeError(f"Failed to create directory for symlink: {e}")
        
        os.symlink(target, link_path)
        
    except OSError as e:
        raise RTTBridgeError(f"Failed to create symlink '{link_path}': {e}")


def main():
    """Main program function."""
    parser = argparse.ArgumentParser(
        description='RTT to PTY bridge using pylink',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available buffers
  %(prog)s -d NRF54L15_M33 -p
  
  # Basic RTT to PTY bridge
  %(prog)s -d NRF54L15_M33 -b Terminal
  
  # With specific RTT address
  %(prog)s -d NRF54L15_M33 -a 0x200044E0
  
  # With search range
  %(prog)s -d NRF54L15_M33 -a 0x20000000,0x2003FFFF
  
  # Bidirectional communication
  %(prog)s -d NRF54L15_M33 -b Terminal --bidir
        """
    )
    parser.add_argument('-d', '--device', default='NRF54L15_M33', 
                       help='Device name (default: NRF54L15_M33)')
    parser.add_argument('-s', '--serial', type=int, 
                       help='J-Link serial number')
    parser.add_argument('-S', '--speed', type=int, default=4000, 
                       help='SWD/JTAG speed in kHz (default: 4000)')
    parser.add_argument('-b', '--buffer', default='Terminal', 
                       help='Buffer name to use (default: Terminal)')
    parser.add_argument('-2', '--bidir', action='store_true', 
                       help='Enable bidirectional communication')
    parser.add_argument('-a', '--address', 
                       help='RTT address (hex) or search range (start,size)')
    parser.add_argument('-l', '--link', 
                       help='Create symlink to PTY at this path')
    parser.add_argument('-p', '--print-bufs', action='store_true', 
                       help='Print list of available buffers and exit')
    
    args = parser.parse_args()
    
    # Validate arguments
    try:
        validate_speed(args.speed)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    if args.address:
        try:
            address_info = parse_address(args.address)
        except ValueError as e:
            print(f"Error: Invalid address format: {e}", file=sys.stderr)
            return 1
    
    if not args.buffer or not args.buffer.strip():
        print("Error: Buffer name cannot be empty", file=sys.stderr)
        return 1
    
    jlink = None
    master_fd = None
    slave_fd = None
    symlink_path = None
    
    try:
        # Connect to J-Link
        try:
            jlink = pylink.JLink()
        except Exception as e:
            print(f"Error: Failed to create J-Link instance: {e}", file=sys.stderr)
            return 1
        
        print("Connecting to J-Link...")
        try:
            if args.serial:
                jlink.open(serial_no=args.serial)
            else:
                jlink.open()
        except pylink.errors.JLinkException as e:
            print(f"Error: Failed to open J-Link: {e}", file=sys.stderr)
            if "No J-Link found" in str(e) or "No connection" in str(e):
                print("Hint: Ensure J-Link is connected and drivers are installed", file=sys.stderr)
            return 1
        
        try:
            if not jlink.opened():
                raise RTTBridgeError("J-Link DLL is not open")
        except RTTBridgeError as e:
            print(f"Error: {e}", file=sys.stderr)
            if jlink:
                jlink.close()
            return 1
        
        print(f"Connecting to {args.device}...")
        try:
            jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
            jlink.set_speed(args.speed)
            jlink.connect(args.device)
        except pylink.errors.JLinkException as e:
            print(f"Error: Failed to connect to device '{args.device}': {e}", file=sys.stderr)
            if jlink:
                jlink.close()
            return 1
        
        # Verify connection after device connect
        try:
            verify_jlink_connection(jlink)
        except RTTBridgeError as e:
            print(f"Error: Connection verification failed: {e}", file=sys.stderr)
            if jlink:
                jlink.close()
            return 1
        
        print("Connected to:")
        try:
            print(f"  {jlink.product_name}")
            print(f"  S/N: {jlink.serial_number}")
        except Exception as e:
            print(f"  (device info unavailable: {e})")
        
        # Configure RTT
        print("Configuring RTT...")
        try:
            if args.address:
                address_info = parse_address(args.address)
                if address_info[1] is not None:
                    # Search range
                    start, size = address_info
                    print(f"Using RTT search range: 0x{start:X}, 0x{size:X}")
                    jlink.rtt_start(search_ranges=[(start, size)])
                else:
                    # Specific address
                    addr = address_info[0]
                    print(f"Using RTT address: 0x{addr:X}")
                    jlink.rtt_start(block_address=addr)
            else:
                print("Using auto-detection for RTT control block...")
                jlink.rtt_start()
        except (pylink.errors.JLinkException, ValueError) as e:
            print(f"Error: Failed to start RTT: {e}", file=sys.stderr)
            if jlink:
                jlink.close()
            return 1
        
        print("Searching for RTT control block...")
        time.sleep(0.5)  # Wait for RTT to initialize
        
        # Verify RTT is active
        max_rtt_wait = 5.0
        rtt_wait_start = time.time()
        while not is_rtt_active(jlink):
            if time.time() - rtt_wait_start > max_rtt_wait:
                print("Error: RTT control block not found after timeout", file=sys.stderr)
                print("Hint: Ensure firmware has RTT enabled and device is running", file=sys.stderr)
                if jlink:
                    try:
                        jlink.rtt_stop()
                    except:
                        pass
                    jlink.close()
                return 1
            time.sleep(0.2)
        
        # Print buffers if requested
        if args.print_bufs:
            success = print_buffers(jlink)
            if jlink:
                jlink.close()
            return 0 if success else 1
        
        # Find buffers
        try:
            index_up, desc_up = find_buffer_by_name(jlink, args.buffer, up=True)
        except RTTBridgeError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("\nAvailable buffers:", file=sys.stderr)
            print_buffers(jlink)
            if jlink:
                jlink.close()
            return 1
        
        if index_up < 0:
            print(f"Error: Failed to find matching up-buffer '{args.buffer}'", 
                  file=sys.stderr)
            print("\nAvailable buffers:", file=sys.stderr)
            print_buffers(jlink)
            if jlink:
                jlink.close()
            return 1
        
        print(f"Using up-buffer #{index_up} '{args.buffer}' (size={desc_up.SizeOfBuffer})")
        
        index_down = -1
        desc_down = None
        if args.bidir:
            try:
                index_down, desc_down = find_buffer_by_name(jlink, args.buffer, up=False)
            except RTTBridgeError as e:
                print(f"Error: {e}", file=sys.stderr)
                print("\nAvailable buffers:", file=sys.stderr)
                print_buffers(jlink)
                if jlink:
                    jlink.close()
                return 1
            
            if index_down < 0:
                print(f"Error: Failed to find matching down-buffer '{args.buffer}'", 
                      file=sys.stderr)
                print("\nAvailable buffers:", file=sys.stderr)
                print_buffers(jlink)
                if jlink:
                    jlink.close()
                return 1
            print(f"Using down-buffer #{index_down} '{args.buffer}' (size={desc_down.SizeOfBuffer})")
        
        # Create PTY
        try:
            master_fd, slave_fd, pty_name = create_pty()
        except RTTBridgeError as e:
            print(f"Error: {e}", file=sys.stderr)
            if jlink:
                jlink.close()
            return 1
        
        print(f"PTY name is {pty_name}")
        
        # Create symlink if requested
        if args.link:
            try:
                create_symlink(pty_name, args.link)
                symlink_path = args.link
                print(f"Created symlink {args.link} -> {pty_name}")
            except RTTBridgeError as e:
                print(f"Warning: {e}", file=sys.stderr)
                print("Continuing without symlink...", file=sys.stderr)
        
        # Configure signals for clean exit
        do_exit = False
        
        def signal_handler(signum, frame):
            nonlocal do_exit
            do_exit = True
            print("\nShutting down...", file=sys.stderr)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGQUIT, signal_handler)
        
        # Main loop
        print("RTT bridge active. Press Ctrl+C to exit.")
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        try:
            while not do_exit:
                # Verify connection is still valid
                try:
                    if not jlink.connected() or not jlink.target_connected():
                        print("\nError: Connection lost", file=sys.stderr)
                        break
                except Exception:
                    print("\nError: Connection check failed", file=sys.stderr)
                    break
                
                # Read from RTT and write to PTY
                try:
                    data = jlink.rtt_read(index_up, 4096)
                    if data:
                        try:
                            bytes_written = os.write(master_fd, bytes(data))
                            if bytes_written != len(data):
                                print(f"\nWarning: Partial write to PTY: {bytes_written}/{len(data)} bytes", 
                                      file=sys.stderr)
                            consecutive_errors = 0
                        except OSError as e:
                            if e.errno == errno.EBADF:
                                print("\nError: PTY file descriptor invalid", file=sys.stderr)
                                break
                            raise
                except pylink.errors.JLinkRTTException:
                    # No data available, this is normal
                    consecutive_errors = 0
                    pass
                except pylink.errors.JLinkException as e:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        print(f"\nError: Too many consecutive J-Link errors: {e}", file=sys.stderr)
                        break
                    time.sleep(0.1)
                    continue
                
                # If bidirectional, read from PTY and write to RTT
                if args.bidir and index_down >= 0:
                    try:
                        ready, _, _ = select.select([master_fd], [], [], 0.1)
                        if ready:
                            try:
                                data = os.read(master_fd, 4096)
                                if data:
                                    try:
                                        bytes_written = jlink.rtt_write(index_down, list(data))
                                        if bytes_written != len(data):
                                            print(f"\nWarning: Partial write to RTT: {bytes_written}/{len(data)} bytes", 
                                                  file=sys.stderr)
                                    except pylink.errors.JLinkRTTException as e:
                                        print(f"\nWarning: Failed to write to RTT buffer: {e}", file=sys.stderr)
                            except OSError as e:
                                if e.errno == errno.EBADF:
                                    print("\nError: PTY file descriptor invalid", file=sys.stderr)
                                    break
                                elif e.errno == errno.EIO:
                                    # PTY closed by slave
                                    print("\nPTY closed by slave", file=sys.stderr)
                                    break
                                raise
                    except select.error as e:
                        if e.args[0] == errno.EBADF:
                            print("\nError: Invalid file descriptor in select", file=sys.stderr)
                            break
                        raise
                else:
                    time.sleep(0.1)
        
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"\nUnexpected error in main loop: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
        finally:
            print("Cleaning up...", file=sys.stderr)
            
            # Stop RTT
            if jlink:
                try:
                    jlink.rtt_stop()
                except Exception as e:
                    print(f"Warning: Failed to stop RTT: {e}", file=sys.stderr)
            
            # Close file descriptors
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
            
            # Remove symlink
            if symlink_path and os.path.exists(symlink_path):
                try:
                    if os.path.islink(symlink_path):
                        os.remove(symlink_path)
                except OSError as e:
                    print(f"Warning: Failed to remove symlink: {e}", file=sys.stderr)
            
            # Close J-Link connection
            if jlink:
                try:
                    jlink.close()
                except Exception as e:
                    print(f"Warning: Failed to close J-Link: {e}", file=sys.stderr)
        
        return 0
        
    except RTTBridgeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except pylink.errors.JLinkException as e:
        print(f"J-Link error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
