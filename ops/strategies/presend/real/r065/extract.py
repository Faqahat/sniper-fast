#!/usr/bin/env python3
"""REPLAY_065 step 2 (read-only on the raw recording): pull every recorded pump.fun tx (successful AND failed) of the tokens
the two runs touched, in the slot ranges that matter, from the 24/7 raw recording (keeper copy in the container).
  ranges per mint: every live pre-send window (trigger - 40 .. window end / sell + 60 slots), every regular fire (dump - 40 ..
  sell + 60), every paper (shadow) window (arm - 40 .. exit + 60)
  also: the per-slot block table (max tx index seen + 1, records, block time) for every slot in the span (the chain clock)
Writes /home/moiz/sniper-data/replay065/raw/{tx.pkl, slots.npy, ranges.json}. Nothing is sent; the recording is only read.
usage: extract.py [--procs 14]"""
import sys, os, re, gzip, json, glob, pickle, collections, time
import numpy as np
from multiprocessing import Pool

REC = "/home/moiz/sniper-data/collect/run_20261026_1415/txs"
OUT = "/home/moiz/sniper-data/replay065/raw"
LIVE = "/home/moiz/sniper-data/replay065/live.pkl"
HEAD = re.compile(r'\{"s":\s*(\d+),\s*"i":\s*(\d+),\s*"bt":\s*(\d+)')
MINTS = re.compile(r'"mints":\s*\[([^\]]*)\]')
T_LO, T_HI = 1793032800 - 600, 1793063700          # 10-26 21:30 .. 10-27 06:15 PKT (unix s)
G = {}


def ranges():
    D = pickle.load(open(LIVE, "rb"))
    R = collections.defaultdict(list)
    def add(m, lo, hi): R[m].append([int(lo) - 40, int(hi) + 60])
    for run, X in D.items():
        for (seg, w), W in X["ps"].items():
            a = W["arm"]; tr = a["trig"]
            hi = a["en_slot"]
            for s in W["sells"]: hi = max(hi, s["slot"])
            for f in W["fills"]: hi = max(hi, f["slot"] + 8)
            add(tr["mint"], tr["slot"], hi)
        for r in X["skips"]:
            tr = r["trig"]; add(tr["mint"], tr["slot"], tr["slot"] + 14)
        for (seg, w), a in X["sh_arm"].items():
            add(a["mint"], a["slot"], a["slot"] + 14)
        for r in X["sh_exit"]:
            add(r["mint"], r["s_in"], r["exit_slot"] + 4)
        for f in X["fires"]:
            d = X["dumps"].get(f.get("dump_sig")) or {}
            s0 = d.get("slot") or f.get("deadline", 0) - 2
            hi = s0 + 20
            for s in X["reg_sell"].get((f["seg"], f["mint"]), []): hi = max(hi, s["slot"])
            add(f["mint"], s0, hi)
    out = {}
    for m, v in R.items():
        v.sort(); mg = []
        for lo, hi in v:
            if mg and lo <= mg[-1][1]: mg[-1][1] = max(mg[-1][1], hi)
            else: mg.append([lo, hi])
        out[m] = mg
    return out


def one(fn):
    want = G["want"]
    keep = []; smax = {}; scnt = {}; sbt = {}
    n = 0; trunc = None
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if not m: continue
                n += 1
                s, i, bt = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if i > smax.get(s, -1): smax[s] = i
                scnt[s] = scnt.get(s, 0) + 1; sbt[s] = bt
                mm = MINTS.search(line)
                if not mm: continue
                hit = False
                for tok in mm.group(1).split(","):
                    k = tok.strip().strip('"')
                    rg = want.get(k)
                    if rg is None: continue
                    for lo, hi in rg:
                        if lo <= s <= hi: hit = True; break
                    if hit: break
                if hit: keep.append(line)
    except (EOFError, OSError) as ex:
        trunc = repr(ex)[:80]
    sl = np.array([(k, smax[k], scnt[k], sbt[k]) for k in sorted(smax)], dtype=[("slot", "u8"), ("maxi", "u4"), ("n", "u4"), ("bt", "u4")])
    return fn, keep, sl, n, trunc


if __name__ == "__main__":
    procs = 14
    if "--procs" in sys.argv: procs = int(sys.argv[sys.argv.index("--procs") + 1])
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    G["want"] = ranges()
    json.dump(G["want"], open(f"{OUT}/ranges.json", "w"))
    files = [f for f in sorted(glob.glob(f"{REC}/txs_*.jsonl.gz")) if T_LO - 310 <= int(os.path.basename(f)[4:14]) <= T_HI]
    print(f"mints {len(G['want'])}, files {len(files)}", flush=True)
    lines = []; slots = []; nl = 0
    with Pool(procs) as p:
        for k, (fn, keep, sl, n, trunc) in enumerate(p.imap_unordered(one, files)):
            lines += keep; slots.append(sl); nl += n
            if trunc: print("TRUNCATED", fn, trunc, flush=True)
            if k % 20 == 0: print(k, os.path.basename(fn), n, len(keep), f"{time.time() - t0:.0f}s", flush=True)
    S = np.concatenate(slots)
    o = np.lexsort((-S["maxi"].astype(np.int64), S["slot"])); S = S[o]
    k2 = np.ones(len(S), bool); k2[1:] = S["slot"][1:] != S["slot"][:-1]; S = S[k2]
    np.save(f"{OUT}/slots.npy", S)
    # parse the kept lines, dedup by signature, group by mint
    bym = collections.defaultdict(list); seen = set(); nd = 0
    for line in lines:
        r = json.loads(line)
        if r["sig"] in seen: nd += 1; continue
        seen.add(r["sig"])
        ev = r.get("ev")
        if isinstance(ev, str):
            try: ev = json.loads(ev)
            except Exception: ev = []
        r["ev"] = ev or []
        for m in set(r.get("mints") or []):
            if m in G["want"]: bym[m].append(r)
    for m in bym: bym[m].sort(key=lambda r: (r["s"], r["i"]))
    pickle.dump(dict(bym), open(f"{OUT}/tx.pkl", "wb"))
    print(f"lines scanned {nl:,}, kept {len(lines):,} (dups {nd}), mints with txs {len(bym)}, slots {len(S):,} {int(S['slot'][0])}->{int(S['slot'][-1])}, {time.time() - t0:.0f}s")
