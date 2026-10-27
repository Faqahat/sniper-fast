#!/usr/bin/env python3
# Shared helpers for the haqq study (read-only, local files only).
import json, os, time, glob, pickle, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq"
W = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
FRA = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"; AMS = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"; US = {FRA, AMS}
HK = "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
SMS = 212.0
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
pkth = lambda t: time.gmtime(int(t) + 18000).tm_hour
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
def svc_of(acc):
    if acc in TIP: return TIP[acc]
    if acc.startswith("noz"): return "nozomi"
    return "?" + acc[:6]
# ---------------- leaders
_LEAD = {}
def _load_leaders():
    if _LEAD: return
    L = json.load(open("/home/moiz/sniper/ops/overnight/landing/work/rpc/leaders.json"))
    _LEAD["map"] = {int(k): v for k, v in L.items()}
    _LEAD["ep"] = {}
    for f in ("/home/moiz/sniper-data/haqq/schedule_1065.json", "/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json", "/home/moiz/sniper-data/competitors2/schedule_1067.json"):
        d = json.load(open(f)); _LEAD["ep"][d["start"]] = (d["ids"], d["slot_leader"])
    nodes = json.load(open("/home/moiz/sniper/ops/overnight/landing/work/rpc/clusternodes_now.json"))["nodes"]
    _LEAD["client"] = {k: v.get("clientId") or "" for k, v in nodes.items()}
    rt = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json"))["leaders"]
    for k, v in rt.items():
        if v.get("client"): _LEAD["client"].setdefault(k, v["client"])
    _LEAD["rtt"] = {k: v.get("rtt") for k, v in rt.items()}
    geo = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_geo.json"))["rows"]
    _LEAD["geo"] = {r["pk"]: (r.get("cc"), r.get("city"), r.get("rtt")) for r in geo}
    for k, v in _LEAD["geo"].items():
        if v[2] is not None: _LEAD["rtt"].setdefault(k, v[2])
def leader(slot):
    _load_leaders()
    ep = slot // 432000 * 432000
    if ep in _LEAD["ep"]:
        ids, sl = _LEAD["ep"][ep]; x = sl[slot - ep]
        return ids[x] if x is not None else None
    return _LEAD["map"].get(slot)
def client_class(c):
    if not c: return "?"
    if "Harmonic" in c: return "harmonic"
    if "Bam" in c or "BAM" in c: return "bam"
    if c == "JitoLabs": return "jito"
    if "dancer" in c: return "fd"
    if c == "Agave": return "agave"
    return "other"
def leader_info(slot):
    ld = leader(slot)
    if ld is None: return None, "?", None, None
    _load_leaders()
    c = _LEAD["client"].get(ld, ""); g = _LEAD["geo"].get(ld, (None, None, None))
    return ld, client_class(c), _LEAD["rtt"].get(ld), g[0]
# ---------------- slot timing (intra-slot position -> ms)
_SS = {}
def slot_size(slot):
    if not _SS:
        for f in ("/home/moiz/sniper/ops/overnight/core/slotsize2.json",):
            _SS.update({int(k): v for k, v in json.load(open(f)).items()})
        for f in glob.glob(f"{OUT}/slotmax_R*.json"):
            for k, v in json.load(open(f)).items():
                k = int(k)
                if k not in _SS: _SS[-k] = v + 1          # lower bound from the recording (negative key = estimate)
    v = _SS.get(slot)
    if v is not None: return v, True
    v = _SS.get(-slot)
    return (v, False) if v is not None else (None, False)
