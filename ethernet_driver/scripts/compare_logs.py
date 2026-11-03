"""Compare what the PC sent with what the board reported receiving.

Takes the sender's CSV (from udp_sender.py) and the board's serial log (from
serial_reader.py). Only the last session in the serial log is used: the board
starts a new session each time it sees seq 0, i.e. each sender run.

For every sent packet it checks that the board received it with status OK and
the same payload length and CRC-32, which proves the bytes arrived unchanged.

Usage:
    python3 compare_logs.py sent.csv received.log

Exit code is 0 only if every sent packet was received intact.
"""

import argparse
import csv
import sys


def load_sent(path):
    sent = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            sent[int(row["seq"])] = (int(row["payload_len"]), row["crc32"].upper())
    return sent


def load_received(path):
    """Return (rx_rows, last_stat, session_count) for the last session."""
    rx, last_stat, sessions = [], None, 0
    with open(path, errors="replace") as f:
        for line in f:
            parts = line.strip().split(",")
            kind = parts[0]
            if kind == "SESSION":
                rx, last_stat = [], None
                sessions += 1
            elif kind == "RX" and len(parts) == 6:
                try:
                    rx.append({
                        "seq": int(parts[1]),
                        "payload_len": int(parts[2]),
                        "crc32": parts[3].upper(),
                        "status": parts[4],
                        "board_ms": int(parts[5]),
                    })
                except ValueError:
                    pass  # garbled line
            elif kind == "STAT":
                last_stat = dict(p.split("=", 1) for p in parts[2:] if "=" in p)
    return rx, last_stat, sessions


def ranges(nums):
    """[1,2,3,7,9,10] -> '1-3, 7, 9-10'"""
    out, nums = [], sorted(nums)
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sent", help="CSV written by udp_sender.py")
    p.add_argument("received", help="serial log written by serial_reader.py")
    p.add_argument("--show", type=int, default=20, help="max problem packets to list per category (default 20)")
    args = p.parse_args()

    sent = load_sent(args.sent)
    rx, stat, sessions = load_received(args.received)
    if sessions == 0:
        print("Note: no SESSION line in the serial log, so the reader may have started after the")
        print("      sender. Using every RX line in the file.")
    elif sessions > 1:
        print(f"Note: {sessions} sessions in the serial log; comparing the last one.")

    ok_rows = [r for r in rx if r["status"] == "OK"]
    bad_rows = [r for r in rx if r["status"] != "OK"]

    received_seqs = {}
    for r in ok_rows:
        received_seqs.setdefault(r["seq"], []).append(r)

    matched, mismatched, unexpected = [], [], []
    for seq, rows in received_seqs.items():
        if seq not in sent:
            unexpected.append(seq)
        elif (rows[0]["payload_len"], rows[0]["crc32"]) == sent[seq]:
            matched.append(seq)
        else:
            mismatched.append(seq)
    missing = [s for s in sent if s not in received_seqs]
    duplicates = [s for s, rows in received_seqs.items() if len(rows) > 1]

    out_of_order, highest = 0, -1
    for r in ok_rows:
        if r["seq"] < highest:
            out_of_order += 1
        highest = max(highest, r["seq"])

    def listing(seqs):
        seqs = sorted(seqs)
        text = ranges(seqs[:args.show])
        return text + (" ..." if len(seqs) > args.show else "")

    print(f"\nSent:                {len(sent)}")
    print(f"Received OK:         {len(ok_rows)}")
    print(f"  matched sent data: {len(matched)}")
    print(f"Missing:             {len(missing)}" + (f"   seq {listing(missing)}" if missing else ""))
    print(f"Data mismatch:       {len(mismatched)}" + (f"   seq {listing(mismatched)}" if mismatched else ""))
    print(f"Not in sent log:     {len(unexpected)}" + (f"   seq {listing(unexpected)}" if unexpected else ""))
    print(f"Duplicates:          {len(duplicates)}")
    print(f"Out of order:        {out_of_order}")
    print(f"Rejected by board:   {len(bad_rows)}", end="")
    if bad_rows:
        by_status = {}
        for r in bad_rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        print("   " + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())), end="")
    print()

    if len(ok_rows) > 1:
        gaps = [b["board_ms"] - a["board_ms"] for a, b in zip(ok_rows, ok_rows[1:])]
        print(f"Board arrival gap:   mean {sum(gaps) / len(gaps):.2f} ms, min {min(gaps)} ms, max {max(gaps)} ms")

    if stat:
        print(f"\nBoard's last STAT:   rx={stat.get('rx')} ok={stat.get('ok')} lost={stat.get('lost')} "
              f"late={stat.get('late')} log_drop={stat.get('log_drop')}")
        if stat.get("rx", "0") != str(len(rx)):
            print("  The board counted a different number of packets than RX lines in the log. Either the")
            print("  reader stopped before the final STAT line, or lines were lost on the serial link.")
        if stat.get("log_drop", "0") != "0":
            print("  log_drop > 0: the board received some packets but could not print them in time, so")
            print("  they show as missing above. Lower --rate or raise the serial baud rate.")
    else:
        print("\nNo STAT line after the session started; let the reader run a second longer next time.")

    passed = not (missing or mismatched or unexpected or bad_rows)
    print("\nPASS: every sent packet arrived intact." if passed else "\nFAIL: see above.")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
