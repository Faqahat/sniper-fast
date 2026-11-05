#!/usr/bin/env python3
"""VULTURE speed probe report (FRA dip34 regular path + VULT_PROBE envelope). Per fire, joined by signature (not mint):
landed?, same slot as the dump, feed clock (dump exec rx -> our buy rx), block-position clock (clock2 land_ms_pos),
first-ness (other buyers between the dump and our buy), followers (other buyers after our buy, up to our sell), P&L.
usage: probe_report.py RUN.jsonl RUN.log"""
import sys, json, re, collections, statistics as st
js, lg = sys.argv[1], sys.argv[2]
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
fires, land, tim, close, tape = [], {}, {}, {}, collections.defaultdict(list)
for l in open(js, errors="replace"):
    d = json.loads(l); e = d.get("ev")
    if e == "fire": fires.append(d)
    elif e == "buy_land": land[d["sig"]] = d
    elif e == "timing": tim[d["buy_sig_seen"]] = d; tim[d["buy_sig"]] = d
    elif e == "close": close[d["buy_sig"]] = d
    elif e == "tape": tape[d["mint"]].append(d)
pnl = collections.defaultdict(list)
for l in open(lg, errors="replace"):
    m = re.search(r"REALIZED mint=(\S+) pnl=([-+0-9.]+)", l)
    if m: pnl[m.group(1)].append(float(m.group(2)))
pi = collections.Counter()
rows = []
for f in fires:
    sigs = {v["sig"] for v in f.get("variants", [])} | {f["buy_sig"]} | {p["sig"] for p in (f.get("nonce") or {}).get("per_path", [])}
    b = next((land[s] for s in sigs if s in land), None)
    r = dict(mint=f["mint"], landed=b is not None)
    if b:
        t = tim.get(b["sig"]) or {}; c2 = t.get("clock2") or {}; c = close.get(b["sig"]) or {}
        ds, di = c.get("dump_slot"), c.get("dump_idx")
        bs, bi = b["slot"], b["idx"]
        sl = (c.get("sell_land") or [None, None])
        oth = [x for x in tape[f["mint"]] if x["buy"] and x["user"] not in OURS]
        before = [x for x in oth if ds is not None and (x["slot"], x["idx"]) > (ds, di) and (x["slot"], x["idx"]) < (bs, bi)]
        after = [x for x in oth if (x["slot"], x["idx"]) > (bs, bi) and (sl[0] is None or (x["slot"], x["idx"]) < (sl[0], sl[1]))]
        k = pi[f["mint"]]; pi[f["mint"]] += 1
        r.update(same=b["slots_after_dump"] == 0, feed=b["rx_ms_after_dump"], pos=c2.get("land_ms_pos"),
                 first=len(before) == 0, n_before=len(before), n_after=len(after), sol_after=sum(x["sol"] for x in after) / 1e9,
                 pnl=pnl[f["mint"]][k] if k < len(pnl[f["mint"]]) else None, sell=float(f.get("sell") or 0))
    rows.append(r)
L = [r for r in rows if r["landed"]]
q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))] if xs else None
feed = [r["feed"] for r in L]; pos = [r["pos"] for r in L if r["pos"] is not None]
print(f"fires {len(rows)}  landed {len(L)} ({100*len(L)/max(1,len(rows)):.0f}%)  failed {len(rows)-len(L)}")
print(f"same slot as dump: {sum(r['same'] for r in L)}/{len(L)} ({100*sum(r['same'] for r in L)/max(1,len(L)):.0f}%)")
print(f"feed clock dump->our buy ms: p25 {q(feed,.25):.1f}  median {st.median(feed):.1f}  p75 {q(feed,.75):.1f}")
if pos: print(f"block-position clock ms:     p25 {q(pos,.25):.1f}  median {st.median(pos):.1f}  p75 {q(pos,.75):.1f}  (n {len(pos)})")
print(f"first buyer after the dump: {sum(r['first'] for r in L)}/{len(L)}; others ahead of us median {st.median([r['n_before'] for r in L])}")
fa = [r for r in L if r["n_after"] > 0]
print(f"followers bought in our hold: {len(fa)}/{len(L)}; median follower SOL {st.median([r['sol_after'] for r in L]):.3f}")
P = [r["pnl"] for r in L if r["pnl"] is not None]
print(f"realized {sum(P):+.4f} SOL over {len(P)} fills; wins {sum(p>0 for p in P)}; with followers {sum(r['pnl'] for r in fa if r['pnl'] is not None):+.4f} ({len(fa)}), without {sum(r['pnl'] for r in L if r['n_after']==0 and r['pnl'] is not None):+.4f} ({len(L)-len(fa)})")
for nm, g in (("same slot", [r for r in L if r["same"]]), ("later slot", [r for r in L if not r["same"]]), ("first", [r for r in L if r["first"]]), ("not first", [r for r in L if not r["first"]])):
    pp = [r["pnl"] for r in g if r["pnl"] is not None]
    print(f"  {nm:10s} n {len(g):3d}  pnl {sum(pp):+.4f}  avg {1000*sum(pp)/max(1,len(pp)):+.1f} mSOL")
