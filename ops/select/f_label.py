#!/usr/bin/env python3
# DEMAND / FOLLOW-THROUGH facts per launch (read-only, offline) for the round-3 filter search. From the exact trade list,
# AFTER the creator's glued bundle (P0 = the post-bundle price, our entry price):
#   outside buyers (not dev / payer / bundle wallets): distinct wallets and buy SOL within 10 s, 60 s, 5 min; outside sells
#   lowest price within 5 s (an immediate dump), price at 60 s / 5 min, graduation (curve filled) and when
# usage: python3 f_label.py <table.jsonl.gz> <phaseA dirs,> <launches.jsonl,> <out.jsonl.gz>
import sys, os, json, gzip, glob, zlib, collections
from multiprocessing import Pool
TAB, PAS, LJS, OUTF = sys.argv[1:5]
L = {}
for p in LJS.split(","):
    for l in open(p):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
TG = {}
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r.get("bt") and r["mint"] in L and r.get("n_trades") and r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200: TG[r["mint"]] = 1
def bucket(m): return zlib.crc32(m.encode()) % 256
W = {"2s": 10, "5s": 25, "10s": 50, "20s": 100, "60s": 300, "5m": 1500}

def work(b):
    tgt = {m for m in TG if bucket(m) == b}
    rows = collections.defaultdict(list); seen = set()
    for pa in PAS.split(","):
        for f in glob.glob(os.path.join(pa, f"b{b:03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    r = json.loads(line)
                    if r[1] not in tgt or (r[5], r[13]) in seen: continue
                    seen.add((r[5], r[13]))
                    rows[r[1]].append((r[2], r[3], r[13], r[5], r[14], r[15] == 1, r[16], r[18], r[19]))
            except (EOFError, OSError, zlib.error): pass
    out = []
    for m, tr in rows.items():
        tr.sort(); c = L[m]; S = c["slot"]; creator = c.get("creator") or c.get("user")
        ci = c.get("idx"); g = set(); prev = ci; gi = 0
        for k, (s, i, j, sig, user, buy, sol, vs, vt) in enumerate(tr):
            if sig == c.get("sig"): gi = k + 1; continue
            if s == S and i in (prev, prev + 1) and buy: g.add(user); prev = i; gi = k + 1
            elif s == S and i > prev + 1: break
            elif s > S: break
        ins = {creator, c.get("user"), c.get("payer")} | g
        pre = tr[gi - 1] if gi > 0 else None
        V0, T0 = (pre[7], pre[8]) if pre and pre[8] else (30_000_000_000, 1_073_000_000_000_000)
        P0 = V0 / T0
        if P0 <= 0: continue
        x = dict(mint=m)
        for w in W: x[f"d_ub_{w}"] = 0; x[f"d_bsol_{w}"] = 0.0; x[f"d_nb_{w}"] = 0; x[f"d_ns_{w}"] = 0
        ub = {w: set() for w in W}; mn5 = 1.0; px60 = px5m = None; grad = None; last_px = 1.0; last_out_buy = None; px = {}
        for s, i, j, sig, user, buy, sol, vs, vt in tr[gi:]:
            d = s - S
            if d > 1500: break
            if vt: last_px = (vs / vt) / P0
            if d <= 25: mn5 = min(mn5, last_px)
            if d <= 300: px60 = last_px
            px5m = last_px
            if grad is None and vs >= 114e9: grad = d
            for w, cap in W.items():
                if d <= cap: px[w] = last_px
            if user in ins: continue
            if buy: last_out_buy = d
            for w, cap in W.items():
                if d <= cap:
                    if buy: ub[w].add(user); x[f"d_bsol_{w}"] += sol / 1e9; x[f"d_nb_{w}"] += 1
                    else: x[f"d_ns_{w}"] += 1
        for w in W: x[f"d_ub_{w}"] = len(ub[w])
        for w in W: x[f"d_px_{w}"] = round(px.get(w, last_px), 4)
        x["d_last_out_buy_s"] = (last_out_buy / 5) if last_out_buy is not None else None   # how long outside buyers kept coming (<= 5 min)
        x.update(d_min5s=round(mn5, 4), d_px60=round(px60 if px60 is not None else 1.0, 4), d_px5m=round(px5m if px5m is not None else 1.0, 4), d_grad_s=(grad / 5) if grad is not None else None)
        out.append(x)
    return out

if __name__ == "__main__":
    with Pool(14) as p: R = [x for part in p.imap_unordered(work, range(256)) for x in part]
    with gzip.open(OUTF, "wt") as f:
        for x in R: f.write(json.dumps(x, separators=(",", ":")) + "\n")
    print("rows", len(R))
