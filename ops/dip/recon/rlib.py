#!/usr/bin/env python3
# Shared helpers for the paper-vs-live reconciliation (ops/dip/recon). Read-only on every input; writes only to WORK.
import os, sys, json, glob, time, re, zlib, gzip, base64, calendar
import numpy as np

LIVE = "/home/moiz/sniper-data/recon/live"
WORK = "/home/moiz/sniper-data/recon/work"
COLLECT = "/home/moiz/sniper-data/collect"
NEW_REC = f"{COLLECT}/run_20261024_1425"
OLD_REC = f"{COLLECT}/run_20261023_1426"
WAL = {"FRA": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "AMS": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
WAL_UID = {zlib.crc32(w.encode()) for w in WAL.values()}
SMS = 212.0
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))


def pkt(t, fmt="%m-%d %H:%M:%S"):
    """unix seconds (float) or ns (int > 1e12) -> PKT string"""
    if t is None: return "-"
    if t > 1e12: t = t / 1e9
    return time.strftime(fmt, time.gmtime(t + 5 * 3600))


def pk(s):
    """'MM-DD HH:MM[:SS]' PKT -> unix seconds"""
    f = "%Y-%m-%d %H:%M:%S" if s.count(":") == 2 else "%Y-%m-%d %H:%M"
    return calendar.timegm(time.strptime("2026-" + s, f)) - 18000


def arrival(s, i):
    """the replay's block-position clock (p1_build.arrival with the default block size 400)"""
    return s * SMS + i / max(400, i + 1) * SMS


def trade_events(r):
    """pump TradeEvents of a recording tx -> list of dicts"""
    out = []
    for e in r.get("ev") or []:
        try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
        except Exception: continue
        if raw[:8] != TRADE or len(raw) < 225: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=b58(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58(raw[57:89]), vsol=u(97), vtok=u(105),
                        fee_bps=u(161), fee=u(169), cfee_bps=u(209), cfee=u(217)))
    return out


RUN_FILES = [("FRA", 10, "dip_r10"), ("FRA", 11, "dip_r11"), ("FRA", 12, "dip_r12"), ("FRA", 13, "dip_r13"), ("FRA", 14, "dip_r14"),
             ("FRA", 15, "dip_r15"), ("AMS", 9, "dip_ams_r9"), ("AMS", 10, "dip_ams_r10"), ("AMS", 11, "dip_ams_r11"),
             ("AMS", 12, "dip_ams_r12"), ("AMS", 13, "dip_ams_r13"), ("AMS", 14, "dip_ams_r14")]


def load_runs():
    """every live run -> dict(srv, run, start, end, cfg, fires=[...]) ; each fire carries its linked records"""
    runs = []
    for srv, rn, base in RUN_FILES:
        recs = []
        for l in open(f"{LIVE}/{base}.jsonl"):
            if '"ev": "dump"' in l[:200] or '"ev":"dump"' in l[:200]:
                continue
            try: o = json.loads(l)
            except Exception: continue
            if o.get("ev") in ("dump",) or o.get("ev", "").startswith("presend"): continue
            recs.append(o)
        st = next(o for o in recs if o["ev"] == "run_start")
        en = next((o for o in recs if o["ev"] == "run_end"), None)
        fires = []; by_sig = {}; by_dump = {}
        for o in recs:
            if o["ev"] == "fire":
                sigs = [o["buy_sig"]]
                if o.get("nonce"):
                    sigs += [p["sig"] for p in o["nonce"].get("per_path", [])]
                    sigs += [v["sig"] for v in o["nonce"].get("variants", [])]
                f = dict(srv=srv, run=rn, fire=o, sigs=list(dict.fromkeys(sigs)), mint=o["mint"], dump_sig=o["dump_sig"])
                fires.append(f)
                for s in f["sigs"]: by_sig[s] = f
                by_dump[(o["dump_sig"], o["mint"])] = f
        last_open = {}
        for o in recs:
            ev = o["ev"]
            if ev == "fire":
                last_open[o["mint"]] = by_dump[(o["dump_sig"], o["mint"])]
            elif ev in ("buy_land", "buy_failed", "land_poll"):
                f = by_sig.get(o.get("sig")) or last_open.get(o.get("mint"))
                if f is not None: f.setdefault(ev, o)
            elif ev == "timing":
                f = by_sig.get(o.get("buy_sig")) or by_sig.get(o.get("buy_sig_seen"))
                if f is not None: f.setdefault("timing", o)
            elif ev in ("exit", "sell_land"):
                f = last_open.get(o.get("mint"))
                if f is not None: f.setdefault(ev, o)
            elif ev == "close":
                f = by_dump.get((o.get("dump_sig"), o.get("mint"))) or by_sig.get(o.get("buy_sig"))
                if f is not None: f["close"] = o
            elif ev == "pick":
                pass
        # REALIZED lines (chain truth per sold position), in order
        rl = []
        for l in open(f"{LIVE}/{base}.log", errors="replace"):
            m = re.search(r"REALIZED mint=(\S+) pnl=([+-][0-9.]+) SOL source=(\S+)", l)
            if m: rl.append((m.group(1), float(m.group(2)), m.group(3)))
        sold = [f for f in fires if f.get("close", {}).get("result") == "sold"]
        used = [False] * len(rl)
        for f in sold:
            for k, (m, p, src) in enumerate(rl):
                if not used[k] and m == f["mint"]:
                    used[k] = True; f["realized"] = p; f["realized_src"] = src; break
        runs.append(dict(srv=srv, run=rn, base=base, start=st["t"] / 1e9, end=(en["t"] / 1e9 if en else None), cfg=st, fires=fires,
                         realized_unmatched=[rl[k] for k in range(len(rl)) if not used[k]]))
    return runs


def load_ours():
    """our wallets' txs found in the recordings (r01_grep_ours.sh output) -> {sig: rec}"""
    out = {}
    for d in ("new", "old"):
        for f in sorted(glob.glob(f"{WORK}/ours/{d}/*.ours.jsonl")):
            for l in open(f):
                try: r = json.loads(l)
                except Exception: continue
                r["_rec"] = d
                if r["sig"] in out and out[r["sig"]]["_rec"] == "new": continue
                out[r["sig"]] = r
    return out


def our_delta(r):
    """our wallet's SOL change (lamports) in a recording tx"""
    tot = 0
    for a, v in r.get("sd") or []:
        if a in WAL.values(): tot += v
    return tot


# ---- slot leaders (epoch schedules) and the near-leader lists the servers used
SCHED_FILES = ["/home/moiz/sniper-data/haqq/schedule_1065.json", "/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json",
               "/home/moiz/sniper-data/competitors2/schedule_1067.json"]
NEAR_FILES = {"FRA": "/home/moiz/sniper/ops/region/near_leaders_fra.txt", "AMS": "/home/moiz/sniper/ops/region/near_leaders_ams.txt",
              "AMS_NOBAM": "/home/moiz/sniper/ops/region/near_leaders_ams_nobam.txt"}
_SC = None


def leader(slot):
    global _SC
    if _SC is None:
        _SC = []
        for f in SCHED_FILES:
            if os.path.exists(f):
                s = json.load(open(f)); _SC.append((s["start"], s["slot_leader"], s["ids"]))
    for st, sl, ids in _SC:
        o = slot - st
        if 0 <= o < len(sl): return ids[sl[o]]
    return None


def near_list(name):
    return {l.strip() for l in open(NEAR_FILES[name]) if l.strip()}


def near_name(srv, run):
    return "AMS_NOBAM" if (srv == "AMS" and run >= 14) else srv
