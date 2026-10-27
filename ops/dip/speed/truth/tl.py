#!/usr/bin/env python3
# SPEED TRUTH shared helpers (read-only study, 10-25). Constants, clocks, leader lookup, percentiles.
import json, os, time, collections
import numpy as np

LIVE = "/home/moiz/sniper-data/recon/live"
OUT = "/home/moiz/sniper-data/speed_truth"
COLLECT = "/home/moiz/sniper-data/collect"
FRA = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
AMS = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
OURS = {FRA, AMS}
SMS = 212.0            # slot length (ms) of the block-position clock (engine measured 211.6)
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
HKQ7 = "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
NAMED = {  # wallets named in the brief / earlier studies
    "Dk2jdQ93k7NjHNWxm5sAqPqPv89raYSjjsmvteo2wgER": "Dk2jdQ93", "A9KKBdLy7VU8vrN8FZcVN5o4MmhkpFextqeKJX9ZZX2u": "A9KKBdLy",
    HAQQ: "haqqiUUX", HKQ7: "HkQ7hMjy", "G9G3dCBGjM1chfZJHvb722zzzm9FQfZi4KbLVGncGeTy": "G9G3dCBG",
    "5w8xtjc649Z628jVvJkwQE5p9aMhV2cUSWr8RVV9BieU": "5w8xtjc6", "6n2cCJrrEAi4SZbBquj9mffUGAFXhDBmFeQEi3maSRcx": "6n2cCJrr",
    "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk": "8PgC4ngp", "9k78QZywYyqUZvZrk1tDuE9qPUbZAz2aFbjUneihdgFX": "9k78QZyw",
    "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXDDrZC", "CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx": "CZ77onJz",
    "6VzXcLk9rCLDHgRBmUGKK8HY2KvhHmR4pZPCxi4tA1kx": "6VzXcLk9",
}
PROS = {HKQ7, HAQQ, "G9G3dCBGjM1chfZJHvb722zzzm9FQfZi4KbLVGncGeTy", "5w8xtjc649Z628jVvJkwQE5p9aMhV2cUSWr8RVV9BieU",
        "6n2cCJrrEAi4SZbBquj9mffUGAFXhDBmFeQEi3maSRcx", "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk",
        "9k78QZywYyqUZvZrk1tDuE9qPUbZAz2aFbjUneihdgFX", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw",
        "CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx", "6VzXcLk9rCLDHgRBmUGKK8HY2KvhHmR4pZPCxi4tA1kx"}
COHORT = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/cohort_R1.json")))   # ~537 consistent-winner bots (R1 study)

RUNS = [("FRA", n, f"dip_r{n}") for n in (10, 11, 13, 14, 15)] + [("AMS", n, f"dip_ams_r{n}") for n in (9, 10, 11, 12, 13, 14)]

pkt = lambda t_s: time.strftime("%m-%d %H:%M:%S", time.gmtime(t_s + 18000))


def bpos(s, i, size=None):
    """block-position clock (ms): slot x 212 + idx / max(400, idx+1) x 212 (size given: idx / max(size, idx+1))"""
    return s * SMS + i / max(size or 400, i + 1) * SMS


def pct(v, ps=(10, 50, 90), fmt="{:.1f}"):
    v = [x for x in v if x is not None]
    if not v: return "-"
    return " / ".join(fmt.format(x) for x in np.percentile(v, ps))


def med(v):
    v = [x for x in v if x is not None]
    return float(np.median(v)) if v else None


def client_class(c):
    if not c: return "?"
    if "Harmonic" in c: return "harmonic"
    if c == "FireBAM": return "firebam"
    if "Bam" in c or "BAM" in c: return "bam"
    if c == "JitoLabs": return "jito"
    if "dancer" in c: return "fd"
    if c == "Agave": return "agave"
    if c == "Rakurai": return "rakurai"
    return "other"


# ---------------- leaders (schedules for epochs 1066 / 1067; client + RTT from the leader books)
_L = {}
def _load():
    if _L: return
    _L["ep"] = {}
    for f in ("/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json", "/home/moiz/sniper-data/competitors2/schedule_1067.json",
              "/home/moiz/sniper-data/haqq/schedule_1065.json"):
        d = json.load(open(f)); _L["ep"][d["start"]] = (d["ids"], d["slot_leader"])
    fra = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json"))["leaders"]
    ams = json.load(open("/home/moiz/sniper/ops/region/leader_rtt_ams.json"))["leaders"]
    _L["client"] = {k: v.get("client") for k, v in fra.items()}
    for k, v in ams.items(): _L["client"].setdefault(k, v.get("client"))
    _L["rtt"] = {"FRA": {k: v.get("rtt") for k, v in fra.items()}, "AMS": {k: v.get("rtt") for k, v in ams.items()}}
    geo = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_geo.json"))["rows"]
    _L["geo"] = {r["pk"]: (r.get("city"), r.get("cc")) for r in geo}


def leader(slot):
    _load()
    ep = slot // 432000 * 432000
    if ep not in _L["ep"]: return None
    ids, sl = _L["ep"][ep]; x = sl[slot - ep]
    return ids[x] if x is not None else None


def leader_client(pk):
    _load(); return _L["client"].get(pk)


def leader_rtt(pk, srv):
    _load(); return _L["rtt"][srv].get(pk)


def leader_geo(pk):
    _load(); return _L["geo"].get(pk, (None, None))


def turn_pos(slot):
    """position of the slot inside its leader's turn (0..3) by walking back while the leader stays the same"""
    ld = leader(slot)
    k = 0
    while k < 8 and leader(slot - k - 1) == ld: k += 1
    return k
