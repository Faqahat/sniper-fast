#!/usr/bin/env python3
# AFTER THE SELLS (read-only, offline): on the model's picks, what does the price do
#  (A) after the creator side (dev + glued-bundle wallets) has SOLD OUT (holds <= 5% of its peak holding)?
#      we buy 0.5 SOL at the end of the sell-out trade's slot (our buy lands ~75 ms after we see it) and hold / exit
#  (B) after our FINAL-1 exit (first sell, end of that slot): how much higher does the price go later (money left)?
# Exact bonding-curve replay of everyone's real trades (same math as training), pump fee per side, 0.015 SOL fixed.
# usage: python3 after_sells.py <table_all.jsonl.gz> <model.json> <phaseA dirs,> <launches.jsonl,> <run2 start bt> <out json>
import sys, os, json, gzip, glob, zlib, math, statistics, collections
from multiprocessing import Pool
TAB, MOD, PAS, LJS, FWD0, OUTF = sys.argv[1:7]; FWD0 = float(FWD0)
X = 493827160; FIX = 0.015; SIZE = 0.5; SPS = 5            # slots per second (as training: 30 s = 150 slots)
HZ = {"5s": 25, "15s": 75, "30s": 150, "60s": 300, "2m": 600, "5m": 1500}
M = json.load(open(MOD)); THR = M["thresholds"]["2%"]
def score(x):
    f = M["F0"]; bins = []
    for k, e in zip(M["features"], M["edges"]):
        if "==" in k: a, v = k.split("==", 1); val = 1.0 if str(x.get(a)) == v else 0.0
        else:
            v = x.get(k); val = float(v) if isinstance(v, (int, float)) and v is not None and not (isinstance(v, float) and math.isnan(v)) else float("nan")
        if math.isnan(val): bins.append(0); continue
        lo, hi = 0, len(e)
        while lo < hi:
            mid = (lo + hi) // 2
            if e[mid] <= val: lo = mid + 1
            else: hi = mid
        bins.append(lo + 1)
    for t in M["trees"]:
        n = t
        while "w" not in n: n = n["l"] if bins[n["f"]] <= n["b"] else n["r"]
        f += M["lr"] * n["w"]
    return f
L = {}
for p in LJS.split(","):
    for l in open(p):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
INFO = {}
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r.get("quote_sol") != 1 or not r.get("bt") or not r.get("n_trades") or (r.get("max_vsol") or 0) > 200 or r["mint"] not in L: continue
    INFO[r["mint"]] = dict(pick=score(r) >= THR, fwd=r["bt"] >= FWD0, bundle=(r.get("glued_n") or 0) >= 1, dev=r.get("dev_buy") or 0)
def bucket(m): return zlib.crc32(m.encode()) % 256

def ret_path(tr, k0, V, T, fb, cb, S0):
    """our 0.5 SOL buy at state (V,T) before tr[k0:]; value at horizons (slots after S0), price peak, tp/sl, trail"""
    P_in = V / T; q = T * X // (V + X); V += X; T -= q; cost = X * (1 + (fb + cb) / 1e4)
    val = lambda V, T: (V * q // (T + q)) * (1 - (fb + cb) / 1e4) / cost - 1
    out = {}; hz = sorted(HZ.items(), key=lambda x: x[1]); hi = 0; pk60 = pk5m = 1.0; tp = None; tr_pk = -1; trail = None
    for t in tr[k0:]:
        d = t["s"] - S0
        while hi < len(hz) and d > hz[hi][1]: out[hz[hi][0]] = val(V, T); hi += 1
        if tp is None and d > 300: tp = val(V, T)
        if trail is None and d > 600: trail = val(V, T)
        if d > 1500: break
        if t["buy"]: dd = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= dd
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        v = val(V, T); px = ((V - X) / (T + q)) / P_in if T + q else 1   # market price without our own impact
        if d <= 300: pk60 = max(pk60, px)
        pk5m = max(pk5m, px)
        if tp is None and (v >= 0.20 or v <= -0.10): tp = v
        if trail is None:
            tr_pk = max(tr_pk, v)
            if (tr_pk >= 0.20 and v <= tr_pk - 0.10) or v <= -0.15: trail = v
    for k, _ in hz[hi:]: out[k] = val(V, T)
    out["tp20_sl10_60s"] = tp if tp is not None else val(V, T); out["trail20_10_2m"] = trail if trail is not None else val(V, T)
    out["pk60"] = pk60; out["pk5m"] = pk5m
    return out

def work(b):
    tgt = {m for m in INFO if bucket(m) == b}
    if not tgt: return []
    rows = collections.defaultdict(list); seen = set()
    for pa in PAS.split(","):
        for f in glob.glob(os.path.join(pa, f"b{b:03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    r = json.loads(line)
                    if r[1] not in tgt: continue
                    k = (r[5], r[13])
                    if k in seen: continue
                    seen.add(k)
                    rows[r[1]].append(dict(s=r[2], i=r[3], j=r[13], sig=r[5], user=r[14], buy=r[15] == 1, sol=r[16], tok=r[17], vsol=r[18], vtok=r[19], fbps=r[22], cbps=r[23]))
            except (EOFError, OSError, zlib.error): pass
    res = []
    for m, tr in rows.items():
        tr.sort(key=lambda t: (t["s"], t["i"], t["j"])); c = L[m]; S = c["slot"]
        creator = c.get("creator") or c.get("user")
        ci = c.get("idx"); g = []; prev = ci; gi = 0
        for k, t in enumerate(tr):
            if t["sig"] == c.get("sig"): gi = k + 1; continue
            if t["s"] == S and t["i"] in (prev, prev + 1) and t["buy"]: g.append(t); prev = t["i"]; gi = k + 1
            elif t["s"] == S and t["i"] > prev + 1: break
            elif t["s"] > S: break
        ins = {creator, c.get("user"), c.get("payer")} | {t["user"] for t in g}
        fb, cb = (tr[0]["fbps"] or 95), (tr[0]["cbps"] or 30)
        hold = collections.Counter(); mx = 0; k_out = None; k_first = None
        for k, t in enumerate(tr):
            if t["user"] not in ins: continue
            hold[t["user"]] += t["tok"] if t["buy"] else -t["tok"]
            tot = sum(max(v, 0) for v in hold.values()); mx = max(mx, tot)
            if not t["buy"] and k_first is None: k_first = k
            if not t["buy"] and mx > 0 and tot <= 0.05 * mx: k_out = k; break
        r = dict(mint=m, **INFO[m], create=c.get("sig"), n=len(tr))
        pre = tr[gi - 1] if gi > 0 else None
        P0 = pre["vsol"] / pre["vtok"] if pre and pre["vtok"] else None
        if k_out is not None and P0:
            so = tr[k_out]["s"]; k0 = next((k for k in range(k_out, len(tr)) if tr[k]["s"] > so), len(tr))
            st = tr[k0 - 1]
            if st["vtok"]:
                r.update(out_s=round((so - S) / SPS, 1), out_sig=tr[k_out]["sig"], out_px_vs_bundle=round((st["vsol"] / st["vtok"]) / P0, 3),
                         buys_left=sum(1 for t in tr[k0:] if t["buy"] and t["s"] - so <= 300))
                r["A"] = {k: round(v, 4) for k, v in ret_path(tr, k0, st["vsol"], st["vtok"], fb, cb, so).items()}
        # (B) FINAL-1 exit: first sell after the bundle, end of its slot; the market price later vs our exit price
        kf = next((k for k in range(gi, len(tr)) if not tr[k]["buy"]), None)
        if kf is not None and P0:
            sf = tr[kf]["s"]; ke = next((k for k in range(kf, len(tr)) if tr[k]["s"] > sf), len(tr)); st = tr[ke - 1]
            if st["vtok"]:
                Pe = st["vsol"] / st["vtok"]
                later = [(t["vsol"] / t["vtok"]) / Pe for t in tr[ke:] if t["vtok"] and t["s"] - sf <= 1500]
                r["B"] = dict(exit_s=round((sf - S) / SPS, 1), exit_vs_bundle=round(Pe / P0, 3), pk60=round(max([x for x, t in zip(later, tr[ke:]) if t["s"] - sf <= 300] + [1.0]), 3),
                              pk5m=round(max(later + [1.0]), 3), end5m=round(later[-1], 3) if later else 1.0)
        res.append(r)
    return res

if __name__ == "__main__":
    with Pool(14) as p: R = [x for part in p.imap_unordered(work, range(256)) for x in part]
    json.dump(R, open(OUTF, "w"))
    def show(lab, rs):
        a = [r for r in rs if "A" in r]
        print(f"\n== {lab}: {len(rs)} launches; creator side sold out (<=5% left) within data: {len(a)} ({len(a) / max(len(rs), 1):.0%})")
        if not a: return
        print(f"   sold out after: median {statistics.median(r['out_s'] for r in a):.0f} s; price then vs right after the bundle: median {statistics.median(r['out_px_vs_bundle'] for r in a):.2f}x;"
              f" outside buys in the next 60 s: median {statistics.median(r['buys_left'] for r in a):.0f}")
        for th in (1.2, 1.5, 2.0):
            print(f"   price rises >= {th}x after the sell-out: within 60 s {sum(1 for r in a if r['A']['pk60'] >= th) / len(a):.0%}, within 5 min {sum(1 for r in a if r['A']['pk5m'] >= th) / len(a):.0%}")
        for k in ("5s", "15s", "30s", "60s", "2m", "5m", "tp20_sl10_60s", "trail20_10_2m"):
            v = [r["A"][k] * SIZE - FIX for r in a]
            print(f"   buy after sell-out, exit {k:14}: mean {statistics.mean(v):+.4f} SOL  median {statistics.median(v):+.4f}  win {sum(1 for x in v if x > 0) / len(v):.0%}  total {sum(v):+.2f} SOL")
        b = [r for r in rs if "B" in r]
        if b:
            print(f"   (B) after OUR exit (first sell, end of slot, median {statistics.median(r['B']['exit_s'] for r in b):.1f} s): price later vs our exit price -> peak within 60 s median {statistics.median(r['B']['pk60'] for r in b):.2f}x,"
                  f" >=1.5x in 60 s {sum(1 for r in b if r['B']['pk60'] >= 1.5) / len(b):.0%}, >=2x in 5 min {sum(1 for r in b if r['B']['pk5m'] >= 2) / len(b):.0%}; price at 5 min vs exit median {statistics.median(r['B']['end5m'] for r in b):.2f}x")
    P = [r for r in R if r["pick"]]
    show("MODEL PICKS (top 2%, all data)", P)
    show("MODEL PICKS, forward data only (not used for training)", [r for r in P if r["fwd"]])
    show("ALL launches with a creator bundle (baseline)", [r for r in R if r["bundle"]])
    show("ALL SOL launches (baseline)", R)
