# rtt2pty-pylink

Python implementation of an RTT to PTY bridge using pylink. This is functionally equivalent to [rtt2pty](https://github.com/codecoup/tools-rtt2pty), but uses pylink instead of directly calling libjlinkarm.so via dlopen.

**Repository:** [https://github.com/fxd0h/rtt2py_pylink](https://github.com/fxd0h/rtt2py_pylink)

## What it does

The script connects to a J-Link debugger, configures RTT (Real-Time Transfer), finds the specified RTT buffers, and creates a pseudo-terminal (PTY) that bridges the RTT communication. Data from the target device flows through RTT buffers and appears on the PTY, making it accessible as a standard terminal device.

## Requirements

- Python 3.7 or higher
- pylink library from <https://github.com/fxd0h/pylink-nrf54-rttFix>
- SEGGER J-Link Software with libjlinkarm.so installed

### Why this specific pylink version?

This project uses a modified version of pylink (<https://github.com/fxd0h/pylink-nrf54-rttFix>) rather than the original Square/pylink repository. The modified version includes important improvements to RTT Control Block (CB) detection that are essential for reliable operation across various devices.

The key improvements include:

- **Enhanced RTT Control Block detection**: Improved search algorithm and multiple stop/start cycles to ensure clean RTT state before detection
- **Better search range handling**: Proper implementation of `SetRTTSearchRanges` command according to SEGGER documentation (UM08001)
- **Increased wait times**: Additional delays after setting search ranges and after START command to allow RTT to properly initialize
- **Device state verification**: Ensures the target device is running before attempting RTT start, as RTT requires an active CPU

These changes address issues where RTT auto-detection could fail on some devices, especially when the control block location is not known in advance. The original pylink implementation had limitations that could cause RTT detection to fail silently or timeout incorrectly.

## Usage

Basic usage - connect to device and bridge default Terminal buffer:

```bash
python3 rtt2pty_pylink.py -d NRF54L15_M33 -b Terminal
```

List available RTT buffers:

```bash
python3 rtt2pty_pylink.py -d NRF54L15_M33 -p
```

Specify RTT control block address directly:

```bash
python3 rtt2pty_pylink.py -d NRF54L15_M33 -a 0x200044E0
```

Use search range for RTT auto-detection:

```bash
python3 rtt2pty_pylink.py -d NRF54L15_M33 -a 0x20000000,0x2003FFFF
```

Enable bidirectional communication (read from PTY and write to RTT):

```bash
python3 rtt2pty_pylink.py -d NRF54L15_M33 -b Terminal --bidir
```

Create a symlink to the PTY for easier access:

```bash
python3 rtt2pty_pylink.py -d NRF54L15_M33 -b Terminal -l /tmp/rtt
```

Select specific J-Link by serial number:

```bash
python3 rtt2pty_pylink.py -d NRF54L15_M33 -s 12345678
```

## Command line options

- `-d, --device`: Target device name (default: NRF54L15_M33)
- `-s, --serial`: J-Link serial number
- `-S, --speed`: SWD/JTAG speed in kHz (default: 4000)
- `-b, --buffer`: RTT buffer name to use (default: Terminal)
- `-2, --bidir`: Enable bidirectional communication
- `-a, --address`: RTT control block address (hex) or search range (start,size)
- `-l, --link`: Create symlink to PTY at specified path
- `-p, --print-bufs`: Print list of available buffers and exit

## How it works

The implementation uses pylink's RTT API which provides all the necessary functionality:

1. **Connection**: Opens J-Link connection using `jlink.open()` and `jlink.connect()`
2. **RTT Configuration**: Configures RTT search ranges or specific address using `jlink.rtt_start()`
3. **Buffer Discovery**: Finds buffers by name using `rtt_get_buf_descriptor()` in a loop
4. **PTY Creation**: Creates pseudo-terminal using Python's `pty.openpty()` module
5. **Data Transfer**: Reads from RTT buffers with `rtt_read()` and writes to PTY, optionally reading from PTY and writing back with `rtt_write()`

All RTT operations available in rtt2pty are available in pylink:

- `rtt_start()` - Start RTT with optional search ranges or specific address
- `rtt_get_num_up_buffers()` / `rtt_get_num_down_buffers()` - Get buffer counts
- `rtt_get_buf_descriptor()` - Get buffer information by index
- `rtt_read()` - Read data from RTT buffer
- `rtt_write()` - Write data to RTT buffer
- `rtt_stop()` - Stop RTT session

The main difference from rtt2pty is that pylink provides a higher-level Python API instead of direct C function calls. This makes the code simpler and easier to maintain while providing the same functionality.

## Comparison with rtt2pty

The original rtt2pty uses dlopen to load libjlinkarm.so and calls C functions directly:

```c
jlink_emu_selectbyusbsn(opt_sn);
jlink_open();
jlink_execcommand("device=NRF54L15_M33", NULL, 0);
jlink_tif_select(1);
jlink_setspeed(4000);
jlink_connect();
jlink_rtterminal_control(RTT_CONTROL_START, NULL);
```

With pylink, the equivalent is:

```python
jlink = pylink.JLink()
jlink.open(serial_no=opt_sn)
jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
jlink.set_speed(4000)
jlink.connect('NRF54L15_M33')
jlink.rtt_start()
```

The pylink version is cleaner and handles errors through exceptions rather than return codes. PTY creation is also simpler using Python's standard library:

```python
master_fd, slave_fd = pty.openpty()
pty_name = os.ttyname(slave_fd)
```

Instead of the C version requiring multiple system calls:

```c
int fdm = posix_openpt(O_RDWR);
grantpt(fdm);
unlockpt(fdm);
printf("PTY name is %s\n", ptsname(fdm));
```

## Implementation details

The script implements a main loop that:

1. Reads data from the RTT UP buffer (target to host)
2. Writes that data to the PTY master file descriptor
3. If bidirectional mode is enabled, reads from PTY and writes to RTT DOWN buffer (host to target)

The loop uses select() for non-blocking PTY reads when bidirectional mode is active, and sleeps briefly when no data is available to avoid busy-waiting.

Signal handlers are set up for SIGINT, SIGTERM, and SIGQUIT to allow clean shutdown. On exit, the script stops RTT, closes file descriptors, and removes any symlinks that were created.

## Finding buffers by name

The script searches through available buffers to find one matching the specified name:

```python
def find_buffer_by_name(jlink, name, up=True):
    num_buffers = (jlink.rtt_get_num_up_buffers() if up 
                  else jlink.rtt_get_num_down_buffers())
    for index in range(num_buffers):
        desc = jlink.rtt_get_buf_descriptor(index, up)
        if desc.name.decode('utf-8').rstrip('\x00') == name:
            return index, desc
    return -1, None
```

This matches the functionality of rtt2pty's buffer search, which iterates through buffers and compares names using strcmp().

## Author

**Mariano Abad (fxd0h)**  
Email: weimaraner@gmail.com  
GitHub: [@fxd0h](https://github.com/fxd0h)

## Repository

**GitHub:** [https://github.com/fxd0h/rtt2py_pylink](https://github.com/fxd0h/rtt2py_pylink)

## References

- Original rtt2pty: <https://github.com/codecoup/tools-rtt2pty>
- pylink library: <https://github.com/fxd0h/pylink-nrf54-rttFix> - RTT API in `pylink/jlink.py` (RTT functions around lines 5329-6092)
- Python pty module: <https://docs.python.org/3/library/pty.html>
