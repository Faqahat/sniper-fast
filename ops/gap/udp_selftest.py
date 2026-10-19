#!/usr/bin/env python3
"""Self-test of the udp-shreds listener: sends synthetic legacy data shreds (one tick entry per data set) to
127.0.0.1:PORT. Local only; nothing leaves the host. Usage: udp_selftest.py PORT [n_slots]"""
import socket, struct, sys, time
port = int(sys.argv[1]); nslots = int(sys.argv[2]) if len(sys.argv) > 2 else 5
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
base = 400_000_000
for k in range(nslots):
    slot = base + k
    for idx in range(64):
        # payload: one serialized Vec<Entry> = [count=1][num_hashes][hash 32][ntx=0]
        payload = struct.pack("<Q", 1) + struct.pack("<Q", 12500) + bytes(32) + struct.pack("<Q", 0)
        flags = 0x40 | (0x80 if idx == 63 else 0)   # DATA_COMPLETE each shred (one set per shred); last in slot
        size = 88 + len(payload)
        hdr = bytes(64) + bytes([0xA5]) + struct.pack("<QIHI", slot, idx, 1234, idx) + struct.pack("<HBH", 1, flags, size)
        s.sendto(hdr + payload + bytes(1228 - size), ("127.0.0.1", port))
    time.sleep(0.05)
print(f"sent {nslots*64} synthetic shreds to 127.0.0.1:{port}")
