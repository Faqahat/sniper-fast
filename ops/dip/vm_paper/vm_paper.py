#!/usr/bin/env python3
# VM1 PAPER TRADE (owner 10-25 morning: "do paper trade on this"). ZERO COST, fully offline: no server, no sends.
# Every 5 min: the newest raw-recording files (local copy, ~10 min behind) -> every >= 1 SOL dump scored by the FROZEN VM1
# (ops/dip/speed/night/vm_frozen.pkl) -> picks (score >= cut) paper-traded at OUR landing: entry = curve just before the dump index
# + 80 txs, +5% guard vs the post-dump price (else a revert: -0.00015), 0.3 SOL, 1.25% pump fee per side, cheap sends 0.0006 SOL per
# filled round trip, exit = curve 6 slots later, gains cut 20% (followers our buy prices out). At most 3 open positions (12 slots each).
# Ledger: vm_paper.jsonl (one line per paper trade), summary: python3 vm_paper.py --report
import json, glob, os, sys, time, pickle, gzip, collections, bisect, numpy as np, subprocess
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip"); sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/night")
import gbdt_np as G
from hq2 import vm_feats
D = os.path.dirname(os.path.abspath(__file__)); LED = f"{D}/vm_paper.jsonl"; ST = f"{D}/state.json"
M = pickle.load(open("/home/moiz/sniper/ops/dip/speed/night/vm_frozen.pkl", "rb"))
S = 0.3e9; FEE = 0.0125; COST = 0.0006; OFF = 80; HOLD = 6; MAXOPEN = 3
def score(x):
    B = np.zeros((1, len(x)), np.int16)
    for j, e in enumerate(M["edges"]): B[0, j] = 0 if np.isnan(x[j]) else np.searchsorted(e, x[j], side="right") + 1
    f = M["F0"]
    for t in M["trees"]: f += M["lr"] * G.pred(t, B)[0]
    return float(f)
def report():
    L = [json.loads(l) for l in open(LED)] if os.path.exists(LED) else []
    if not L: print("no paper trades yet"); return
    pk = [x for x in L if x["result"] != "skipped_max_open"]; fill = [x for x in pk if x["result"] == "filled"]
    h = (L[-1]["slot"] - L[0]["slot"]) * 0.2126 / 3600
    pnl = sum(x["pnl"] for x in pk)
    print(f"VM1 paper: {h:.1f} h | picks {len(L)} | taken {len(pk)} (skipped, 3 open: {len(L)-len(pk)}) | filled {len(fill)} reverted {len(pk)-len(fill)} | P&L {pnl:+.3f} SOL"
          f" | per taken trade {pnl/max(len(pk),1):+.4f} | win {sum(1 for x in fill if x['pnl']>0)}/{len(fill)} | {pnl/max(h,0.01)*24:+.1f} SOL/day")
    by = collections.defaultdict(list)
    for x in pk: by[time.strftime("%H", time.gmtime(x["bt"] + 5 * 3600))].append(x["pnl"])
    print("  by PKT hour: " + " | ".join(f"{k}h {sum(v):+.2f} ({len(v)})" for k, v in sorted(by.items())))
if "--report" in sys.argv: report(); sys.exit()
st = json.load(open(ST)) if os.path.exists(ST) else {"done": [], "open_until": [], "start": time.time()}
while True:
    runs = sorted(glob.glob("/home/moiz/sniper-data/collect/run_*/txs"))
    files = sorted(f for r in runs[-2:] for f in glob.glob(f"{r}/txs_*.jsonl.gz"))
    new = [f for f in files if f not in st["done"] and int(os.path.basename(f)[4:14]) >= 1792900000]    # from 10-25 ~05:40 PKT on
    if len(new) >= 2:
        win = files[max(0, files.index(new[0]) - 6): files.index(new[-1])]                              # 30 min of history + new, the newest file stays (still being written)
        T = collections.defaultdict(list)
        for f in win:
            try:
                with gzip.open(f, "rt") as fh:
                    for l in fh:
                        if '"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"' not in l: continue
                        r = json.loads(l)
                        if r.get("err") is not None: continue
                        import base64
                        for e in r.get("ev") or []:
                            try: b = base64.b64decode(e)
                            except ValueError: continue          # a malformed event: skip it, never the file
                            if len(b) < 113 or b[:8] != bytes([189, 219, 127, 211, 78, 230, 97, 238]): continue
                            u = lambda o: int.from_bytes(b[o:o + 8], "little")
                            if 25e9 <= u(97) <= 200e9: T[b[8:40].hex()].append((r["s"], r["i"], b[57:89].hex(), b[56] == 1, u(40), u(48), u(97), u(105), r.get("bt")))
            except (EOFError, OSError, ValueError): pass
        lo = min(int(os.path.basename(f)[4:14]) for f in new[:-1]); hi = max(int(os.path.basename(f)[4:14]) for f in new[:-1]) + 300
        out = []
        for m, v in T.items():
            v.sort(); slots = [x[0] for x in v]; keys = [(x[0], x[1]) for x in v]
            for k, x in enumerate(v):
                if x[3] or x[4] < 1e9 or not x[8] or not (lo <= x[8] < hi): continue
                if keys[-1][0] < x[0] + HOLD + 1: continue            # exit not recorded yet
                sc = score(vm_feats(v, slots, k))
                if sc < M["cut"]: continue
                kp = bisect.bisect_left(keys, (x[0], x[1] + 1)) - 1; ke = bisect.bisect_left(keys, (x[0], x[1] + 1 + OFF)) - 1
                pv, ev = v[kp], v[ke]
                rec = dict(mint=m, slot=x[0], idx=x[1], bt=x[8], vm=round(sc, 4), dump_sol=x[4] / 1e9)
                if (ev[6] / ev[7]) / (pv[6] / pv[7]) > 1.05: rec.update(result="reverted", pnl=-0.00015)
                else:
                    xin = S * (1 - FEE); q = ev[7] * xin / (ev[6] + xin)
                    xv = v[bisect.bisect_left(keys, (x[0] + HOLD + 1, 0)) - 1]
                    p = ((xv[6] + xin) * q / xv[7] * (1 - FEE) - S) / 1e9 - COST
                    rec.update(result="filled", pnl=round(p * 0.8 if p > 0 else p, 6), entry_vs_dump=round((ev[6] / ev[7]) / (pv[6] / pv[7]), 4))
                out.append(rec)
        out.sort(key=lambda r: (r["slot"], r["idx"]))
        with open(LED, "a") as fh:
            for r in out:
                st["open_until"] = [s for s in st["open_until"] if s > r["slot"]]
                if len(st["open_until"]) >= MAXOPEN: r = dict(r, result="skipped_max_open", pnl=0.0)
                else: st["open_until"].append(r["slot"] + 12)
                fh.write(json.dumps(r) + "\n")
        st["done"] += new[:-1]; json.dump(st, open(ST, "w"))
    time.sleep(300)
