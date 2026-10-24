#!/usr/bin/env python3
# ANTI-DUMP features (read-only, offline). Per launch, from the exact trade list: when the creator side (dev + glued
# bundle wallets) first sells and when it has sold out, and each insider wallet's own first-sell delay. Then LEAK-FREE
# behaviour history (only launches whose 10-minute window ended before this create, same rule as c_join): how fast did
# THIS creator's / THESE bundle wallets' earlier launches dump?  Everything here is computable live from the collector.
# (GDM forward copy of ops/select/f_dump.py: Pool(14) -> Pool(6), nothing else)
# usage: python3 f_dump.py <table.jsonl.gz> <phaseA dirs,> <launches.jsonl,> <out.jsonl.gz>
import sys, os, json, gzip, glob, zlib, statistics, collections
from multiprocessing import Pool
TAB, PAS, LJS, OUTF = sys.argv[1:5]
L = {}
for p in LJS.split(","):
    for l in open(p):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
BT = {}
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r.get("bt") and r["mint"] in L: BT[r["mint"]] = (r["bt"], r.get("creator"), r.get("n_trades") or 0)
def bucket(m): return zlib.crc32(m.encode()) % 256
FAST_FIRST, FAST_OUT = 25, 75                               # insiders sell within 5 s / sold out within 15 s (slots, 5/s)

def work(b):
    tgt = {m for m, v in BT.items() if v[2] and bucket(m) == b}
    if not tgt: return []
    rows = collections.defaultdict(list); seen = set()
    for pa in PAS.split(","):
        for f in glob.glob(os.path.join(pa, f"b{b:03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    r = json.loads(line)
                    if r[1] not in tgt or (r[5], r[13]) in seen: continue
                    seen.add((r[5], r[13]))
                    rows[r[1]].append((r[2], r[3], r[13], r[5], r[14], r[15] == 1, r[17]))
            except (EOFError, OSError, zlib.error): pass
    out = []
    for m, tr in rows.items():
        tr.sort(); c = L[m]; S = c["slot"]; creator = c.get("creator") or c.get("user")
        ci = c.get("idx"); g = []; prev = ci
        for s, i, j, sig, user, buy, tok in tr:
            if sig == c.get("sig"): continue
            if s == S and i in (prev, prev + 1) and buy: g.append(user); prev = i
            elif s == S and i > prev + 1: break
            elif s > S: break
        gw = sorted(set(g)); ins = {creator, c.get("user"), c.get("payer")} | set(gw)
        hold = collections.Counter(); mx = 0; first = out_d = None; wfirst = {}
        for s, i, j, sig, user, buy, tok in tr:
            d = s - S
            if d > 2860: break
            if user not in ins: continue
            hold[user] += tok if buy else -tok
            tot = sum(max(v, 0) for v in hold.values()); mx = max(mx, tot)
            if not buy:
                if first is None: first = d
                wfirst.setdefault(user, d)
                if out_d is None and mx > 0 and tot <= 0.05 * mx: out_d = d
        fast = int((first is not None and first <= FAST_FIRST) or (out_d is not None and out_d <= FAST_OUT))
        out.append(dict(mint=m, gw=gw, dev=c.get("user"), first=first, out=out_d, fast=fast,
                        wsell={w: wfirst.get(w) for w in set(gw) | {c.get("user")} if w}))
    return out

if __name__ == "__main__":
    with Pool(6) as p: F = {x["mint"]: x for part in p.imap_unordered(work, range(256)) for x in part}
    order = sorted(BT, key=lambda m: BT[m][0])
    hc = collections.defaultdict(list); hw = collections.defaultdict(list); pend = collections.deque(); res = []
    med = lambda v: statistics.median(v) if v else None
    for m in order:
        t, cr, _ = BT[m]
        while pend and pend[0][0] <= t:                          # resolve launches whose 10-minute window has ended
            _, pm = pend.popleft(); x = F.get(pm)
            if x is None: continue
            hc[BT[pm][1]].append((x["fast"], x["first"] if x["first"] is not None else 2860, x["out"] if x["out"] is not None else 2860))
            for w, d in x["wsell"].items(): hw[w].append(d if d is not None else 2860)
        x = F.get(m, {}); gw = x.get("gw") or []; dv = x.get("dev")
        h = hc.get(cr, []); ws = [hw[w] for w in gw if w in hw]; dvh = hw.get(dv, []) if dv else []
        allw = [d for v in ws for d in v]
        res.append(dict(mint=m, fast=x.get("fast"), ins_first_s=(x["first"] / 5) if x.get("first") is not None else None,
                        ins_out_s=(x["out"] / 5) if x.get("out") is not None else None,
                        hd_cr_n=len(h), hd_cr_fast=(sum(a[0] for a in h) / len(h)) if h else None,
                        hd_cr_first_s=(med([a[1] for a in h]) / 5) if h else None, hd_cr_out_s=(med([a[2] for a in h]) / 5) if h else None,
                        hd_bw_seen=len(ws), hd_bw_n=len(allw), hd_bw_fast=(sum(1 for d in allw if d <= FAST_FIRST) / len(allw)) if allw else None,
                        hd_bw_first_s=(med(allw) / 5) if allw else None,
                        hd_bw_worst=(max(sum(1 for d in v if d <= FAST_FIRST) / len(v) for v in ws)) if ws else None,
                        hd_dev_n=len(dvh), hd_dev_fast=(sum(1 for d in dvh if d <= FAST_FIRST) / len(dvh)) if dvh else None))
        pend.append((t + 600, m))
    with gzip.open(OUTF, "wt") as f:
        for r in res: f.write(json.dumps(r, separators=(",", ":")) + "\n")
    with gzip.open(OUTF.replace(".jsonl.gz", "") + ".raw.jsonl.gz", "wt") as f:     # raw facts: the live scorer's seed history
        for m in order:
            x = F.get(m)
            if x: f.write(json.dumps(dict(mint=m, bt=BT[m][0], creator=BT[m][1], fast=x["fast"], first=x["first"], out=x["out"], wsell=x["wsell"]), separators=(",", ":")) + "\n")
    n = len(res); print("rows", n, "with trades", sum(1 for r in res if r["fast"] is not None), "fast-dump rate", sum(1 for r in res if r["fast"]) / max(1, sum(1 for r in res if r["fast"] is not None)))
