"""HILU packet format, shared by the sender and the log tools.

Must match the layout in Inc/udp_receiver.h. All fields little-endian:

    offset  size  field
    0       4     magic         b"HILU"
    4       1     version       1
    5       1     msg_type      1 (data)
    6       2     payload_len   N
    8       4     seq           starts at 0 for each sender run
    12      8     host_time_us  sender timestamp
    20      N     payload
    20+N    4     crc32         zlib.crc32 of bytes 0 .. 20+N-1
"""

import struct
import zlib

MAGIC = b"HILU"
VERSION = 1
TYPE_DATA = 1

HEADER = struct.Struct("<4sBBHIQ")
CRC = struct.Struct("<I")

# 1500 MTU - 20 IP - 8 UDP: largest packet that is never IP-fragmented
MAX_PACKET = 1472
MAX_PAYLOAD = MAX_PACKET - HEADER.size - CRC.size

DEFAULT_IP = "192.168.0.10"
DEFAULT_PORT = 5005
DEFAULT_BAUD = 921600


def build_packet(seq, payload, host_time_us):
    """Return (packet_bytes, crc32) for one data packet."""
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload is {len(payload)} bytes, max is {MAX_PAYLOAD}")
    body = HEADER.pack(MAGIC, VERSION, TYPE_DATA, len(payload), seq & 0xFFFFFFFF, host_time_us) + payload
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return body + CRC.pack(crc), crc


def format_crc(crc):
    """CRC as the board prints it, e.g. '0A1B2C3D'."""
    return f"{crc:08X}"
