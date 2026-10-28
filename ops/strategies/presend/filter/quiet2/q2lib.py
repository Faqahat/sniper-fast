#!/usr/bin/env python3
"""QUIET2 shared: the live runs' records -> windows (one per presend_live_arm) with their tries, fills, sells, realized P&L,
rent back, the QUIET signals, the skips; times in PKT. Read-only."""
import json, gzip, collections, datetime

D = "/home/moiz/sniper-data/presend_filter/quiet2"
AMS = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
FRA = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
OURS = {AMS, FRA}
RUNS = collections.OrderedDict([
    ("a28", dict(file=f"{D}/ams_r28.jsonl.gz", wallet=AMS, name="AMS r28", role="train")),
    ("a29", dict(file=f"{D}/ams_r29.jsonl.gz", wallet=AMS, name="AMS r29", role="train")),
    ("a30", dict(file=f"{D}/ams_r30.jsonl.gz", wallet=AMS, name="AMS r30", role="train")),
    ("a31", dict(file=f"{D}/ams_r31.jsonl.gz", wallet=AMS, name="AMS r31", role="train")),
    ("a32", dict(file=f"{D}/ams_r32.jsonl.gz", wallet=AMS, name="AMS r32", role="train")),
    ("a33", dict(file=f"{D}/ams_r33.jsonl.gz", wallet=AMS, name="AMS r33", role="train")),
    ("f27", dict(file="/home/moiz/sniper-data/runs/fra/runs/dip_r27.jsonl", wallet=FRA, name="FRA r27", role="train")),
    ("f28", dict(file="/home/moiz/sniper-data/runs/fra/runs/dip_r28.jsonl", wallet=FRA, name="FRA r28", role="test")),
    ("a34", dict(file=f"{D}/ams_r34.jsonl.gz", wallet=AMS, name="AMS r34", role="test")),
])


def pkt(ns, f="%m-%d %H:%M:%S"):
    return (datetime.datetime.fromtimestamp(ns / 1e9, datetime.UTC) + datetime.timedelta(hours=5)).strftime(f)


def opener(fn):
    return gzip.open(fn, "rt") if fn.endswith(".gz") else open(fn, errors="ignore")


def load(run):
    """windows of one run: dict (seg, w) -> window; also skips (list), run meta"""
    R = RUNS[run]; seg = 0
    W = collections.OrderedDict(); att = {}; skips = []; meta = {"starts": [], "ends": []}; tape = collections.defaultdict(list)
    shadow = {}
    with opener(R["file"]) as f:
        for line in f:
            if '"ev":"' not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            ev = r.get("ev")
            if ev == "run_start":
                seg += 1; meta["starts"].append(r); continue
            if ev == "run_end": meta["ends"].append(r); continue
            k = (seg, r.get("w"))
            if ev == "presend_live_arm":
                W[k] = dict(run=run, seg=seg, w=r["w"], arm=r, mint=r["trig"]["mint"], whale=r["trig"]["wallet"], t=r["trig"]["t"], trig_slot=r["trig"]["slot"],
                            spend=r["spend"], tries=[], fills=[], sells=[], realized=None, close=None, exit=None, disarm=None, ata=[], skip=False)
            elif ev == "presend_live_skip":
                r["seg"] = seg; skips.append(r)
            elif ev == "presend_attempt":
                att[r["sig"]] = dict(a=r, land=None)
                if k in W: W[k]["tries"].append(r["sig"])
            elif ev == "presend_attempt_land":
                if r["sig"] in att: att[r["sig"]]["land"] = r
            elif ev == "presend_live_fill":
                if k in W: W[k]["fills"].append(r)
            elif ev == "presend_live_sell_land":
                if k in W: W[k]["sells"].append(r)
            elif ev == "presend_live_realized":
                if k in W: W[k]["realized"] = r
            elif ev == "presend_live_close":
                if k in W: W[k]["close"] = r
            elif ev == "presend_live_exit":
                if k in W: W[k]["exit"] = r
            elif ev == "presend_live_disarm":
                if k in W: W[k]["disarm"] = r
            elif ev == "presend_live_ata_close":
                tape[("ata", r["mint"])].append(r)
            elif ev == "presend_live_tape":
                tape[r["mint"]].append(r)
            elif ev in ("presend_arm", "presend_disarm", "presend_fill", "presend_exit"):
                shadow.setdefault((seg, r.get("w")), {})[ev] = r
    # attach: tries with land; the ATA close for each filled window (by mint, the first unused after the sell)
    used = set()
    for w in W.values():
        w["tries"] = [att[s] for s in w["tries"] if s in att]
        if w["fills"]:
            for a in tape.get(("ata", w["mint"]), []):
                if id(a) in used: continue
                if a["slot"] >= w["fills"][0]["slot"]:
                    w["ata"].append(a); used.add(id(a)); break
        w["tape"] = tape.get(w["mint"], [])
    return W, skips, meta, shadow


def win_pnl(w):
    """net SOL of the window: realized pnl (lamports; sells - buys incl. fees/tips) + ATA rent back - failed-try fees; None if not settled"""
    fees_failed = sum((t["land"] or {}).get("fee", 0) for t in w["tries"] if t["land"] and (t["land"].get("res") not in (None, "ok", "fill")) and not t["land"].get("filled"))
    return fees_failed


def try_fee(t):
    """the fee of a failed try (0 for a filled one or one never landed)"""
    l = t["land"]
    if not l: return 0
    if l.get("err") is None and l.get("res") in ("ok", "landed", "fill"): return 0
    return l.get("fee", 0) or 0
