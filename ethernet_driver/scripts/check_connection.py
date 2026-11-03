"""Check that the board is reachable over Ethernet (run on the Windows PC).

1. Ping: the board must reply with TTL=255 (lwIP's default). TTL 64 or 128
   means some other host answered.
2. HTTP GET on port 80: the firmware still serves ST's demo web page.

Usage:
    python check_connection.py [--ip 192.168.0.10]
"""

import argparse
import platform
import re
import subprocess
import sys
import urllib.request

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


def check_http(ip, timeout):
    url = f"http://{ip}/"
    print(f"HTTP GET {url} ...")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("latin-1")
            title = re.search(r"<title>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
            print(f"  OK: HTTP {resp.status}, {len(body)} bytes"
                  + (f", title: {title.group(1).strip()!r}" if title else ""))
            return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ip", default=DEFAULT_IP, help=f"board IP (default {DEFAULT_IP})")
    p.add_argument("--count", type=int, default=4, help="ping count (default 4)")
    p.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout in seconds (default 3)")
    args = p.parse_args()

    ping_ok = check_ping(args.ip, args.count)
    http_ok = check_http(args.ip, args.timeout)
    print("\nAll checks passed." if ping_ok and http_ok else "\nSome checks failed.")
    sys.exit(0 if ping_ok and http_ok else 1)


if __name__ == "__main__":
    main()
