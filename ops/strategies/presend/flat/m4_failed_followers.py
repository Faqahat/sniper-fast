#!/usr/bin/env python3
"""FLAT study (descriptive, MEASURED on the raw recording): failed pump.fun txs of OTHER wallets on the token while a flat position
was held (from our buy's slot to our sell's slot) and in the 2 slots after our sell, by error code. A failed buy with a slippage
error (6042 buy below min tokens out / 6002 too much SOL required) inside the hold is a follower our buy may have priced out
(upper bound: its limit is not in the recording). usage: m4_failed_followers.py r24 r25 r26 r27 r28"""
import sys, os, re, gzip, json, glob, collections, time
from multiprocessing import Pool
import flatlib as FL

REC = "/home/moiz/sniper-data/collect"
HEAD = re.compile(r'\{"s":\s*(\d+),\s*"i":\s*(\d+),\s*"bt":\s*(\d+)')
G = {}

def one(fn):
    want = G["want"]; out = []
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                if '"err":null' in line: continue
                m = HEAD.match(line)
                if not m: continue
                s = int(m.group(1))
                if s < G["smin"] or s > G["smax"]: continue
                hit = [mm for mm in want if mm in line]
                if not hit: continue
                r = json.loads(line)
                for mm in hit:
                    for (a, b, key) in want[mm]:
                        if a <= s <= b:
                            err = r.get("err"); code = None
                            try:
                                ie = err.get("InstructionError"); c = ie[1]; code = c.get("Custom") if isinstance(c, dict) else str(c)
                            except Exception: code = str(err)[:30]
                            out.append((key, s, r["i"], (r.get("signers") or ["?"])[0], code, tuple((r.get("ixn") or [])[:4])))
    except (EOFError, OSError):
        pass
    return out

def main():
    runs = sys.argv[1:]
    want = collections.defaultdict(list); smin = 10**12; smax = 0; info = {}
    for run in runs:
        for w in FL.load_base(run)["W"]:
            if not w["filled"] or not w.get("flat"): continue
            a = w["fill"]["slot"]; b = w["sells"][-1]["slot"] + 2
            key = (run, w["seg"], w["w"]); want[w["mint"]].append((a, b, key)); info[key] = (w["spend"], w["mint"], w["sells"][-1]["slot"])
            smin = min(smin, a); smax = max(smax, b)
    G["want"] = dict(want); G["smin"] = smin; G["smax"] = smax
    files = []
    for d in sorted(glob.glob(f"{REC}/run_2026102[567]_*")):
        for f in glob.glob(f"{d}/txs/txs_*.jsonl.gz"):
            ts = int(os.path.basename(f)[4:14])
            if 1793030000 <= ts <= 1793117000: files.append(f)
    t0 = time.time()
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(one, files): res += o
    res = sorted(set(res))
    ours = {FL.AMS, FL.FRA}
    per = collections.defaultdict(list)
    for (key, s, i, sg, code, ixn) in res:
        if sg in ours: continue
        per[key].append((s, i, sg, code, ixn))
    tot = collections.Counter(); bysize = collections.defaultdict(collections.Counter)
    for key, (spend, mint, sell_slot) in info.items():
        L = per.get(key, [])
        slip_in = [x for x in L if x[3] in (6042, 6002) and x[0] <= sell_slot]
        any_in = [x for x in L if x[0] <= sell_slot]
        tot["flats"] += 1; tot["with_any_failed_other_tx_in_hold"] += bool(any_in); tot["with_slippage_failed_buy_in_hold"] += bool(slip_in)
        bysize[spend / 1e9]["flats"] += 1; bysize[spend / 1e9]["with_slippage_failed_buy_in_hold"] += bool(slip_in)
    codes = collections.Counter(x[3] for L in per.values() for x in L)
    print(f"scanned {len(files)} chunks in {time.time() - t0:.0f}s; flat positions {len(info)}")
    print(dict(tot)); print({k: dict(v) for k, v in bysize.items()}); print("error codes of other wallets' failed txs on these tokens (hold + 2 slots):", codes.most_common(12))
main()
