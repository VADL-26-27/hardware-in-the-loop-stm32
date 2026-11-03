"""Read the board's serial log from the ST-LINK virtual COM port (run on the Mac).

Writes every line the board prints to a log file (default received.log)
for compare_logs.py, and shows the once-per-second STAT lines live.

Usage:
    python3 serial_reader.py                     # auto-detect the ST-LINK port
    python3 serial_reader.py --port /dev/tty.usbmodem1103 --verbose

Start this before udp_sender.py, and after the sender finishes wait for one
more STAT line (about a second) before pressing Ctrl-C.

Requires pyserial: python3 -m pip install pyserial
"""

import argparse
import glob
import sys

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial is not installed. Run: python3 -m pip install pyserial")

from protocol import DEFAULT_BAUD

ST_VID = 0x0483


def find_port():
    st_ports = [p.device for p in list_ports.comports() if p.vid == ST_VID]
    # macOS lists both /dev/cu.* and /dev/tty.*; either works
    candidates = st_ports or sorted(glob.glob("/dev/tty.usbmodem*") + glob.glob("/dev/ttyACM*"))
    if not candidates:
        sys.exit("No ST-LINK serial port found. Is the board plugged in? Pass --port to choose one.")
    if len(candidates) > 1:
        print(f"Several ports found {candidates}; using {candidates[0]}. Pass --port to choose another.")
    return candidates[0]


def show(line, verbose):
    kind = line.split(",", 1)[0]
    if kind == "RX":
        # Always show bad packets; show good ones only with --verbose
        if verbose or line.split(",")[4:5] != ["OK"]:
            print(line)
    elif kind in ("STAT", "SESSION", "BOOT", "ERR"):
        print(line)
    else:
        print(f"(unrecognised) {line}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="serial port (default: auto-detect ST-LINK)")
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD,
                   help=f"baud rate, must match SERIAL_LOG_BAUDRATE in firmware (default {DEFAULT_BAUD})")
    p.add_argument("--log", default="received.log", help="file to write board output to (default received.log)")
    p.add_argument("--verbose", action="store_true", help="print every RX line, not just errors and STAT")
    args = p.parse_args()

    port = args.port or find_port()
    lines = 0
    with serial.Serial(port, args.baud, timeout=1) as ser, open(args.log, "w") as log:
        ser.reset_input_buffer()
        print(f"Reading {port} at {args.baud} baud, logging to {args.log}. Ctrl-C to stop.")
        try:
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="replace").strip()
                if not line:
                    continue
                log.write(line + "\n")
                lines += 1
                show(line, args.verbose)
        except KeyboardInterrupt:
            pass
    print(f"\nStopped. Wrote {lines} lines to {args.log}.")


if __name__ == "__main__":
    main()
