"""Check that the board is reachable over Ethernet (run on the Windows PC).

Pings the board: it must reply with TTL=255 (lwIP's default). TTL 64 or 128
means some other host answered.

Usage:
    python check_connection.py [--ip 192.168.0.10]
"""

import argparse
import platform
import re
import subprocess
import sys

from protocol import DEFAULT_IP

LWIP_TTL = 255


def check_ping(ip, count):
    flag = "-n" if platform.system() == "Windows" else "-c"
    print(f"Pinging {ip} ({count} packets)...")
    result = subprocess.run(["ping", flag, str(count), ip], capture_output=True, text=True)
    ttls = [int(t) for t in re.findall(r"ttl[=:](\d+)", result.stdout, re.IGNORECASE)]

    if not ttls:
        print("  FAIL: no replies.")
        print("  Check the cable, the board's green LED (LED2), the PC adapter's static IP")
        print("  (192.168.0.11 / 255.255.255.0), and that the firmware is flashed.")
        return False
    print(f"  {len(ttls)}/{count} replies, TTL values: {sorted(set(ttls))}")
    if any(t != LWIP_TTL for t in ttls):
        print(f"  FAIL: expected TTL={LWIP_TTL}. Another device is answering at {ip}.")
        return False
    print("  OK: the board answered.")
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ip", default=DEFAULT_IP, help=f"board IP (default {DEFAULT_IP})")
    p.add_argument("--count", type=int, default=4, help="ping count (default 4)")
    args = p.parse_args()

    sys.exit(0 if check_ping(args.ip, args.count) else 1)


if __name__ == "__main__":
    main()
