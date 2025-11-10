# Testing Documentation

This directory contains test scripts for validating the rtt2pty_pylink functionality.

## Test Scripts

### test_pty_basic.py
Basic PTY functionality tests that don't require a J-Link connection. These tests validate that PTY creation and I/O operations work correctly on the system.

**Usage:**
```bash
python3 test_pty_basic.py
```

**What it tests:**
- PTY creation
- PTY read/write operations
- Non-blocking PTY operations

### test_pty_reader.py
Script to read data from a PTY created by rtt2pty_pylink. Useful for testing the RTT bridge functionality.

**Usage:**
```bash
# Read from PTY with default 30 second timeout
python3 test_pty_reader.py /dev/pts/5

# Read with custom timeout
python3 test_pty_reader.py /dev/pts/5 -t 60

# Read maximum 1024 bytes
python3 test_pty_reader.py /dev/pts/5 -m 1024
```

### test_pty_writer.py
Script to write data to a PTY created by rtt2pty_pylink. Useful for testing bidirectional RTT communication.

**Usage:**
```bash
# Write a string
python3 test_pty_writer.py /dev/pts/5 "Hello RTT"

# Write from stdin
echo "Test" | python3 test_pty_writer.py /dev/pts/5 -

# Write with delay between chunks
python3 test_pty_writer.py /dev/pts/5 "Hello" -d 0.5
```

### test_integration.py
End-to-end integration test that:
1. Starts rtt2pty_pylink in the background
2. Reads from the created PTY
3. Optionally writes to the PTY (if bidirectional mode)
4. Validates data flow

**Usage:**
```bash
# Basic test
python3 test_integration.py -d NRF54L15_M33

# Test with bidirectional mode
python3 test_integration.py -d NRF54L15_M33 --bidir

# Test with specific RTT address
python3 test_integration.py -d NRF54L15_M33 -a 0x200044E0

# Test with custom timeout
python3 test_integration.py -d NRF54L15_M33 -t 20
```

## Running Tests

### Prerequisites
- Python 3.7+
- pylink library installed
- J-Link connected (for integration tests)
- Target device with RTT enabled (for integration tests)

### Quick Test Sequence

1. **Run basic PTY tests** (no hardware required):
   ```bash
   python3 test_pty_basic.py
   ```

2. **Manual integration test**:
   ```bash
   # Terminal 1: Start rtt2pty_pylink
   python3 ../rtt2pty_pylink.py -d NRF54L15_M33 -b Terminal -l /tmp/rtt_test
   
   # Terminal 2: Read from PTY
   python3 test_pty_reader.py /tmp/rtt_test
   
   # Terminal 3 (optional, if bidirectional): Write to PTY
   python3 test_pty_writer.py /tmp/rtt_test "Test message"
   ```

3. **Automated integration test**:
   ```bash
   python3 test_integration.py -d NRF54L15_M33
   ```

## Test Coverage

- ✅ PTY creation and validation
- ✅ PTY read operations
- ✅ PTY write operations
- ✅ Non-blocking I/O
- ✅ RTT bridge end-to-end functionality
- ✅ Bidirectional communication
- ✅ Error handling

## Notes

- Integration tests require a physical J-Link and target device
- Tests may need adjustment based on your specific hardware setup
- Some tests may timeout if RTT is not properly configured in firmware
- Ensure firmware has RTT enabled before running integration tests

