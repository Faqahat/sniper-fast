#!/usr/bin/env python3
# BACKRUN-THE-DUMP strategy (wallet HkQ7hMjy's real pattern: it buys in the SAME block right behind a big sell)
# Derived from the DIP-REBOUND strategy (read-only, offline): after a DUMP (price falls >= D from its running peak since the creator's
# bundle) buy when the price REBOUNDS >= U from the low (the "starts to increase" signal), if that happens within W.
# Our 0.5 SOL buy fills at the end of the signal's slot (we see the trade, land about one slot later); exits are
# take-profit / stop-loss / trailing stop / fixed holds, each with a time cap. Exact bonding-curve replay of everyone's
# real trades (our own curve impact included), pump fee per side from the events, 0.015 SOL fixed per round trip.
# A curve that fills (graduates) while we hold is left out (no AMM price in our data). Settings are chosen on BUILD
# (run 1) and reported on TEST (forward run). usage: python3 dip_test.py <table.jsonl.gz> <phaseA dirs,> <launches,> <run2 start bt> <out json>
import sys, os, json, gzip, glob, zlib, collections, itertools
import numpy as np
from multiprocessing import Pool
TAB, PAS, LJS, FWD0, OUTF = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5]
X = 493827160; FIX = float(os.environ.get("FIX", "0.015")); SPS = 5   # wallet HkQ7 pays ~0.0003 SOL tx fees per round trip, no tip
UNIV = os.environ.get("UNIV", "all")                                 # "wallet": launches like the wallet's (dev buy >= 1 SOL and a creator bundle)                           # 0.5 SOL gross; slots per second (as training)
# grid modelled on wallet HkQ7hMjy (2026-10-23: buys ~25% under the running peak at the low, ~6 s in, after ~18 outside
# buyers; sells ~1.4 s later): dump D, rebound U (0 = buy the dip itself), window W, at least N outside buys before the signal
DUMPS = [0.0, 0.2, 0.3]; UPS = [0.5, 1.0, 2.0]; WINS = {"10s": 50, "30s": 150, "60s": 300}; MINB = [0, 10]   # BACKRUN: UPS holds the big-sell size (SOL)
EXITS = [("hold5blk", ("h", 5)), ("hold7blk", ("h", 7)), ("hold10blk", ("h", 10)), ("hold20blk", ("h", 20)), ("tp5_sl5_10s", ("tp", .05, .05, 50)),
         ("tp10_sl10_10s", ("tp", .10, .10, 50)), ("trail5_3_10s", ("trail", .05, .03, 50, .08)), ("fsell_eos_10s", ("fs", 50))]
L = {}
for p in LJS.split(","):
    for l in open(p):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
INFO = {}
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200 and r.get("bt") and r.get("n_trades", 0) >= 5 and r["mint"] in L \
       and (UNIV != "wallet" or ((r.get("dev_buy") or 0) >= 1 and (r.get("glued_n") or 0) >= 1)):
        INFO[r["mint"]] = dict(bt=r["bt"], fwd=r["bt"] >= FWD0)
def bucket(m): return zlib.crc32(m.encode()) % 256

def run_exit(tr, k0, V, T, fb, cb, S0, ex):
    q = T * X // (V + X); V += X; T -= q; cost = X * (1 + (fb + cb) / 1e4)
    val = lambda V, T: (V * q // (T + q)) * (1 - (fb + cb) / 1e4) / cost - 1
    kind = ex[0]; cap = ex[3] if kind in ("tp", "trail") else ex[1]; pk = -1; fs = None
    for t in tr[k0:]:
        if t[0] - S0 > cap: return val(V, T)
        if fs is not None and t[0] > fs: return val(V, T)          # first sell after our buy: out at the end of its slot
        if t[7] >= 114e9: return None                          # curve filled while we hold
        if t[5]: dd = T * t[6] // (V + t[6]); V += t[6]; T -= dd
        else: so = V * t[8] // (T + t[8]); V -= so; T += t[8]
        v = val(V, T)
        if kind == "fs" and fs is None and not t[5]: fs = t[0]
        if kind == "tp" and (v >= ex[1] or v <= -ex[2]): return v
        if kind == "trail":
            pk = max(pk, v)
            if (pk >= ex[1] and v <= pk - ex[2]) or v <= -ex[4]: return v
    return val(V, T)

def work(b):
    tgt = {m for m in INFO if bucket(m) == b}; out = []
    if not tgt: return out
    rows = collections.defaultdict(list); seen = set()
    for pa in PAS.split(","):
        for f in glob.glob(os.path.join(pa, f"b{b:03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    r = json.loads(line)
                    if r[1] not in tgt or (r[5], r[13]) in seen: continue
                    seen.add((r[5], r[13]))
                    rows[r[1]].append((r[2], r[3], r[13], r[5], r[14], r[15] == 1, r[16], r[18], r[17], r[19], r[22], r[23]))
            except (EOFError, OSError, zlib.error): pass
    for m, tr in rows.items():
        tr.sort(); c = L[m]; S = c["slot"]
        ci = c.get("idx"); prev = ci; gi = 0
        for k, t in enumerate(tr):
            if t[3] == c.get("sig"): gi = k + 1; continue
            if t[0] == S and t[1] in (prev, prev + 1) and t[5]: prev = t[1]; gi = k + 1
            elif t[0] == S and t[1] > prev + 1: break
            elif t[0] > S: break
        if gi == 0 or not tr[gi - 1][9]: continue
        fb, cb = (tr[0][10] or 95), (tr[0][11] or 30)
        px = [(t[7] / t[9]) if t[9] else None for t in tr]
        res = {}
        creator = c.get("creator") or c.get("user"); ins = {creator, c.get("user"), c.get("payer")} | {t[4] for t in tr[:gi] if t[0] == S}
        nob = [0] * len(tr); n = 0
        for k in range(gi, len(tr)):
            if tr[k][5] and tr[k][4] not in ins: n += 1
            nob[k] = n
        for D, U, (wn, W), NB in itertools.product(DUMPS, UPS, WINS.items(), MINB):
            peak = px[gi - 1]; trig = None
            for k in range(gi, len(tr)):
                if tr[k][0] - S > W: break
                p = px[k]
                if p is None: continue
                if tr[k][7] >= 114e9: break
                if p > peak: peak = p
                if not tr[k][5] and tr[k][6] >= U * 1e9 and p <= peak * (1 - D) and nob[k] >= NB: trig = k; break
            if trig is None: continue
            k0 = trig + 1                                       # BACKRUN: right behind the big sell, same block (the wallet's position)
            st = tr[k0 - 1]
            if not st[9] or st[7] >= 114e9: continue
            r = {}
            for en, ex in EXITS:
                v = run_exit(tr, k0, st[7], st[9], fb, cb, st[0], ex)
                if v is not None: r[en] = v * 0.5 - FIX
            res[f"sell{U:g}SOL_drop{int(D * 100)}_{wn}_N{NB}"] = r
        if res: out.append((m, INFO[m]["fwd"], res))
    return out

if __name__ == "__main__":
    with Pool(14) as p: R = [x for part in p.imap_unordered(work, range(256)) for x in part]
    nb = sum(1 for m in INFO if not INFO[m]["fwd"]); nt = len(INFO) - nb
    hb = (max(v["bt"] for v in INFO.values() if not v["fwd"]) - min(v["bt"] for v in INFO.values() if not v["fwd"])) / 3600
    ht = (max(v["bt"] for v in INFO.values() if v["fwd"]) - min(v["bt"] for v in INFO.values() if v["fwd"])) / 3600
    keys = sorted({k for _, _, res in R for k in res}); rows = []
    for k in keys:
        for en, _ in EXITS:
            vb = np.array([res[k][en] for m, f, res in R if not f and k in res and en in res[k]]); vt = np.array([res[k][en] for m, f, res in R if f and k in res and en in res[k]])
            if len(vb) < 30 or len(vt) < 10: continue
            rows.append(dict(rule=k, exit=en, nb=len(vb), mb=float(vb.mean()), wb=float((vb > 0).mean()), sb=float(vb.sum()), hb=float(vb.sum() / hb),
                             nt=len(vt), mt=float(vt.mean()), wt=float((vt > 0).mean()), st=float(vt.sum()), ht=float(vt.sum() / ht), medt=float(np.median(vt))))
    json.dump(dict(rows=rows, build_launches=nb, test_launches=nt, build_h=hb, test_h=ht), open(OUTF, "w"))
    rows.sort(key=lambda r: -r["mb"])
    print(f"BUILD {nb} launches ({hb:.1f} h) | TEST {nt} launches ({ht:.1f} h) | rule = dump D from peak, rebound U from the low, within W")
    print("top 12 by BUILD mean per trade (then TEST, never used to choose):")
    for r in rows[:12]:
        print(f"  {r['rule']:16} {r['exit']:16} BUILD n={r['nb']:5} mean {r['mb']:+.4f} SOL win {r['wb']:.0%} {r['hb']:+.2f} SOL/h | TEST n={r['nt']:5} mean {r['mt']:+.4f} median {r['medt']:+.4f} win {r['wt']:.0%} total {r['st']:+.2f} SOL {r['ht']:+.2f} SOL/h")
    pos = [r for r in rows if r["mb"] > 0]
    print(f"\nsettings positive on BUILD: {len(pos)} of {len(rows)}; of those also positive on TEST: {sum(1 for r in pos if r['mt'] > 0)}")
