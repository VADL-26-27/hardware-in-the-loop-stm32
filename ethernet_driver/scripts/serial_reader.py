"""Read the board's serial log from the ST-LINK virtual COM port (run on the Mac).

Writes every line the board prints to a log file (default received.log)
for compare_logs.py, and shows the once-per-second STAT lines live.

RAW lines (packets not in the HILU test format) that hold a JSON object,
such as the sim's telemetry, are parsed and each one is written as a row of
a CSV (default telemetry.csv), one column per JSON field.

Usage:
    python3 serial_reader.py                     # auto-detect the ST-LINK port
    python3 serial_reader.py --port /dev/tty.usbmodem1103 --verbose
    python3 serial_reader.py --text              # show only the packets' text

Start this before udp_sender.py, and after the sender finishes wait for one
more STAT line (about a second) before pressing Ctrl-C.

Requires pyserial: python3 -m pip install pyserial
"""

import argparse
import csv
import glob
import json
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


def as_text(hex_bytes):
    """The bytes as text if they are all printable ASCII, else None."""
    try:
        data = bytes.fromhex(hex_bytes)
    except ValueError:
        return None
    if data and all(32 <= b < 127 or b in (9, 10, 13) for b in data):
        return data.decode("ascii")
    return None


class TelemetryLog:
    """Parses JSON telemetry from RAW lines and writes it to a CSV."""

    def __init__(self, path, quiet=False):
        self.path = path
        self.quiet = quiet
        self.file = None
        self.writer = None
        self.rows = 0
        self.bad = 0

    def add(self, board_ms, text):
        try:
            fields = json.loads(text)
        except ValueError:
            self.bad += 1
            if not self.quiet:
                print("  json: could not parse (cut off or not JSON)")
            return
        if not isinstance(fields, dict):
            return
        if not self.quiet:
            print("  json: " + " ".join(f"{k}={v}" for k, v in fields.items()))
        if self.writer is None:
            # Columns come from the first packet; later fields not in it are dropped
            self.file = open(self.path, "w", newline="")
            self.writer = csv.DictWriter(self.file, ["board_ms", *fields], extrasaction="ignore")
            self.writer.writeheader()
        self.writer.writerow({"board_ms": board_ms, **fields})
        self.rows += 1

    def close(self):
        if self.file:
            self.file.close()


def show_text_only(line, telemetry):
    """Print only the text of RAW packets; still log JSON telemetry to the CSV."""
    parts = line.split(",")
    if parts[0] != "RAW":
        return
    text = as_text(parts[-1])
    if text:
        print(text.rstrip("\r\n"))
        if text.lstrip().startswith("{"):
            telemetry.add(parts[2], text)


def show(line, verbose, telemetry):
    kind = line.split(",", 1)[0]
    if kind == "RX":
        # Always show bad packets; show good ones only with --verbose
        if verbose or line.split(",")[4:5] != ["OK"]:
            print(line)
    elif kind == "RAW":
        parts = line.split(",")
        text = as_text(parts[-1])
        if text and text.lstrip().startswith("{"):
            telemetry.add(parts[2], text)
            if verbose:
                print(line)
        else:
            print(line)
            if text:
                print(f"  text: {text}")
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
    p.add_argument("--telemetry", default="telemetry.csv",
                   help="CSV to write parsed JSON telemetry to (default telemetry.csv)")
    p.add_argument("--verbose", action="store_true",
                   help="print every RX line, not just errors and STAT, and the hex of JSON packets")
    p.add_argument("--text", action="store_true",
                   help="print only the text of each packet (e.g. the sim's JSON), nothing else")
    args = p.parse_args()

    port = args.port or find_port()
    lines = 0
    telemetry = TelemetryLog(args.telemetry, quiet=args.text)
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
                if args.text:
                    show_text_only(line, telemetry)
                else:
                    show(line, args.verbose, telemetry)
        except KeyboardInterrupt:
            pass
    telemetry.close()
    print(f"\nStopped. Wrote {lines} lines to {args.log}.")
    if telemetry.rows or telemetry.bad:
        print(f"Wrote {telemetry.rows} telemetry rows to {args.telemetry}"
              + (f"; {telemetry.bad} could not be parsed." if telemetry.bad else "."))


if __name__ == "__main__":
    main()
