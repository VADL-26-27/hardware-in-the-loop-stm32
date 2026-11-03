"""Send HILU data packets to the board over UDP (run on the Windows PC).

Every packet sent is logged to a CSV (seq, payload_len, crc32, host_time_us)
so compare_logs.py can check it against what the board reported over serial.

Usage:
    python udp_sender.py --rate 200 --size 64 --duration 10
    python udp_sender.py --ip 192.168.0.10 --port 5005 --count 1000 --payload random

Stop early with Ctrl-C; the log is kept.
"""

import argparse
import csv
import os
import socket
import time

from protocol import DEFAULT_IP, DEFAULT_PORT, MAX_PAYLOAD, build_packet, format_crc


def make_payload(kind, seq, size):
    if kind == "zeros":
        return bytes(size)
    if kind == "random":
        return os.urandom(size)
    # counter: bytes count up from seq, so every packet's content differs
    return bytes((seq + i) & 0xFF for i in range(size))


def wait_until(deadline):
    # Sleep for most of the gap, then spin, for sub-millisecond pacing on Windows
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > 0.002:
            time.sleep(remaining - 0.002)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ip", default=DEFAULT_IP, help=f"board IP (default {DEFAULT_IP})")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"board UDP port (default {DEFAULT_PORT})")
    p.add_argument("--bind", default="", help="local IP to send from, e.g. 192.168.0.11, to force the Ethernet adapter")
    p.add_argument("--rate", type=float, default=200.0, help="packets per second (default 200)")
    p.add_argument("--size", type=int, default=64, help=f"payload bytes, 0..{MAX_PAYLOAD} (default 64)")
    p.add_argument("--payload", choices=["counter", "random", "zeros"], default="counter",
                   help="payload content (default counter)")
    p.add_argument("--count", type=int, default=0, help="packets to send, 0 = no limit (default 0)")
    p.add_argument("--duration", type=float, default=0.0, help="seconds to send, 0 = no limit (default 0)")
    p.add_argument("--log", default="sent.csv", help="CSV log of sent packets (default sent.csv)")
    args = p.parse_args()

    if not 0 <= args.size <= MAX_PAYLOAD:
        p.error(f"--size must be between 0 and {MAX_PAYLOAD}")
    if args.rate <= 0:
        p.error("--rate must be positive")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if args.bind:
        sock.bind((args.bind, 0))
    dest = (args.ip, args.port)
    period = 1.0 / args.rate

    print(f"Sending to {args.ip}:{args.port} at {args.rate:g} Hz, {args.size}-byte {args.payload} payload. "
          f"Logging to {args.log}. Ctrl-C to stop.")

    seq = 0
    late = 0
    start = time.perf_counter()
    next_send = start
    next_report = start + 1.0
    last_report_seq = 0

    with open(args.log, "w", newline="") as f:
        log = csv.writer(f)
        log.writerow(["seq", "payload_len", "crc32", "host_time_us"])
        try:
            while True:
                if args.count and seq >= args.count:
                    break
                if args.duration and time.perf_counter() - start >= args.duration:
                    break

                wait_until(next_send)
                host_time_us = time.time_ns() // 1000
                packet, crc = build_packet(seq, make_payload(args.payload, seq, args.size), host_time_us)
                sock.sendto(packet, dest)
                log.writerow([seq, args.size, format_crc(crc), host_time_us])
                seq += 1

                next_send += period
                now = time.perf_counter()
                if now - next_send > 0.1:
                    # More than 100 ms behind: resync instead of sending a burst
                    late += 1
                    next_send = now

                if now >= next_report:
                    print(f"  sent {seq} packets ({seq - last_report_seq} in the last second)")
                    last_report_seq = seq
                    next_report += 1.0
        except KeyboardInterrupt:
            pass

    elapsed = time.perf_counter() - start
    print(f"Done: sent {seq} packets in {elapsed:.2f} s ({seq / elapsed if elapsed else 0:.1f} Hz).")
    if late:
        print(f"Warning: fell behind the requested rate {late} time(s); the PC could not keep up.")
    sock.close()


if __name__ == "__main__":
    main()
