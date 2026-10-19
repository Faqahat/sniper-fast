# READ-ONLY offline. Per-wallet sniper profile: buy size vs curve state, fees (confidence factor), position, exits, PnL.
# usage: python3 wan.py <wallet> <tx.jsonl> [out.json]
import sys, json, glob, collections, statistics as st, math
W, TXF = sys.argv[1], sys.argv[2]
OUT = sys.argv[3] if len(sys.argv) > 3 else None
V0, T0 = 30_000_000_000, 1_073_000_000_000_000
RENT = 2039280
SYS = "11111111111111111111111111111111"
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}

# launch index from race on-chain labels
L = {}
for fn in glob.glob("/root/race/*_onchain.jsonl"):
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        b = r.get("b") or {}
        if not b or "dev" not in b or r["mint"] in L: continue
        host = (b.get("uri") or "").split("://")[-1].split("/")[0]
        dev = b["dev"] / 1e9; gs = (b.get("gsol") or 0) / 1e9
        moon = any(str(x[2]).startswith("moon") for x in b.get("tips", []))
        base = 0.49 <= dev <= 8.1 and not (host in BOT or host.endswith(".trycloudflare.com")) and "CreateV2" in (b.get("ins") or [])
        pos = {}
        for x in b.get("later") or []:
            if x.get("ok"):
                for p in [x["payer"]] + [e[1] for e in x.get("ev") or []]:
                    pos.setdefault(p, x["d"])
        L[r["mint"]] = dict(slot=b["slot"], bt=b.get("bt"), dev=dev, gsol=gs, moon=moon, r2=base and 2.95 <= gs <= 5.05 and moon,
                            cont=base and gs >= 2, base=base, pos=pos, nlater=len(b.get("later") or []))

TX = []
for l in open(TXF):
    try: TX.append(json.loads(l))
    except Exception: pass
by = collections.defaultdict(lambda: {"ok": [], "fail": []})
for t in TX:
    mine = [e for e in t["ev"] if e["user"] == W]
    if not t["err"] and mine: by[mine[0]["mint"]]["ok"].append(t)
    elif t["err"]:
        for m in t["mints"]: by[m]["fail"].append(t)


def tipinfo(t):
    tips = [(x[0], x[1], x[2] if len(x) > 2 else "") for x in t["tips"]]
    lab = "+".join(sorted({str(x[0])[:10] for x in tips})) or "-"
    return sum(x[1] for x in tips) / 1e9, lab


rows = []
for m, v in by.items():
    okt = sorted(v["ok"], key=lambda t: (t["slot"], t["bt"] or 0))
    evs = [(t, e) for t in okt for e in t["ev"] if e["user"] == W and e["mint"] == m]
    buys = [(t, e) for t, e in evs if e["buy"]]
    sells = [(t, e) for t, e in evs if not e["buy"]]
    if not buys or buys[0][1]["sol"] == 0: continue
    t0, e0 = buys[0]
    f = dict(mint=m, slot=t0["slot"], bt=t0["bt"], sol=e0["sol"] / 1e9, nbuys=len(buys), sig=t0["sig"])
    vp, tp = e0["vsol"] - e0["sol"], e0["vtok"] + e0["tok"]
    f["real_pre"] = (vp - V0) / 1e9; f["mc_pre"] = vp / tp * 1e6
    f["impact"] = (e0["vsol"] / e0["vtok"]) / (vp / tp) - 1
    f["cu"] = t0["cu_price"] or 0; f["cul"] = t0["cu_limit"] or 0
    f["prio"] = f["cu"] * f["cul"] / 1e15
    f["tip"], f["tiplab"] = tipinfo(t0)
    f["land"] = t0["fee"] / 1e9 + f["tip"]
    f["land_pct"] = f["land"] / f["sol"]
    cost = sum(e["sol"] for _, e in buys) / 1e9
    f["pnl"] = (sum(t["dsol"] for t in okt) + RENT - sum(t["fee"] for t in v["fail"])) / 1e9
    f["pnl_pct"] = f["pnl"] / cost
    f["nfail"] = len(v["fail"])
    tot = sum(e["tok"] for _, e in buys)
    px0 = e0["sol"] / e0["tok"]
    f["sells"] = [dict(dt=(t["bt"] or 0) - (t0["bt"] or 0), ds=t["slot"] - t0["slot"], frac=e["tok"] / max(1, tot),
                       pxr=(e["sol"] / max(1, e["tok"])) / px0, land=t["fee"] / 1e9 + tipinfo(t)[0]) for t, e in sells]
    f["sold"] = sum(e["tok"] for _, e in sells) / max(1, tot)
    la = L.get(m)
    if la:
        f.update(dev=la["dev"], gsol=la["gsol"], r2=la["r2"], cont=la["cont"], base=la["base"], dslot=t0["slot"] - la["slot"],
                 pos=la["pos"].get(W) if t0["slot"] == la["slot"] else None)
    rows.append(f)
if OUT: json.dump(rows, open(OUT, "w"))

P = lambda xs, q: sorted(xs)[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")
def r2(x, y):
    if len(x) < 5: return float("nan")
    mx, my = st.mean(x), st.mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y)); sxx = sum((a - mx) ** 2 for a in x); syy = sum((b - my) ** 2 for b in y)
    return (sxy * sxy / (sxx * syy)) if sxx and syy else float("nan")
def corr(x, y):
    v = r2(x, y)
    if math.isnan(v): return v
    mx, my = st.mean(x), st.mean(y)
    return math.copysign(math.sqrt(v), sum((a - mx) * (b - my) for a, b in zip(x, y)))

n = len(rows)
print(f"=== {W[:8]}  first buys {n}  (txs {len(TX)}, failed buy txs {sum(r['nfail'] for r in rows)})")
if not n: sys.exit()
bts = [r["bt"] for r in rows if r["bt"]]
span_h = (max(bts) - min(bts)) / 3600 if bts else 0
tot = sum(r["pnl"] for r in rows)
print(f"span {span_h:.1f} h  buys/h {n / max(span_h, 1e-9):.1f}  PnL total {tot:+.2f} SOL  -> {tot / max(span_h, 1e-9) * 24:+.1f} SOL/day"
      f"  mean {st.mean(r['pnl_pct'] for r in rows) * 100:+.2f}%  median {st.median(r['pnl_pct'] for r in rows) * 100:+.2f}%  win {sum(r['pnl'] > 0 for r in rows) / n * 100:.0f}%"
      f"  avg SOL/trade {tot / n:+.4f}")
sz = [r["sol"] for r in rows]
print(f"SIZE  q10 {P(sz, .1):.3f} q25 {P(sz, .25):.3f} med {P(sz, .5):.3f} q75 {P(sz, .75):.3f} q90 {P(sz, .9):.3f}  max {max(sz):.3f}")
hist = collections.Counter(round(s, 2) for s in sz)
print("  most common sizes:", ", ".join(f"{k}x{c}" for k, c in hist.most_common(10)))
ls = [math.log(r["sol"]) for r in rows]
for k in ("real_pre", "mc_pre", "dev", "gsol", "pos", "dslot"):
    xs = [(r[k], math.log(r["sol"])) for r in rows if r.get(k) is not None]
    if k in ("real_pre", "mc_pre", "dev", "gsol"):
        xs = [(math.log(max(a, 1e-3)), b) for a, b in xs]
    if len(xs) >= 5:
        print(f"  R2 log(size) ~ {k:8} {r2([a for a, _ in xs], [b for _, b in xs]):.3f}  (n={len(xs)})")
print(f"  entry MC SOL q25 {P([r['mc_pre'] for r in rows], .25):.1f} med {P([r['mc_pre'] for r in rows], .5):.1f} q75 {P([r['mc_pre'] for r in rows], .75):.1f}"
      f"   own impact med {P([r['impact'] for r in rows], .5) * 100:.1f}%  q90 {P([r['impact'] for r in rows], .9) * 100:.1f}%")
for lo, hi in ((0, 0.75), (0.75, 1.5), (1.5, 2.5), (2.5, 4), (4, 99)):
    g = [r for r in rows if lo <= r["sol"] < hi]
    if g:
        print(f"  size {lo:>4}-{hi:<3} n={len(g):4}  land med {P([r['land'] for r in g], .5):.4f} SOL ({P([r['land_pct'] for r in g], .5) * 100:.1f}%)"
              f"  pnl mean {st.mean(r['pnl_pct'] for r in g) * 100:+.1f}% med {st.median(r['pnl_pct'] for r in g) * 100:+.1f}%"
              f"  win {sum(r['pnl'] > 0 for r in g) / len(g) * 100:.0f}%  SOL/trade {st.mean(r['pnl'] for r in g):+.4f}")
print("FEES  land q25 {:.4f} med {:.4f} q75 {:.4f} q90 {:.4f}   prio med {:.4f}  tip med {:.4f}  CU price med {:.0f}  CU limit med {:.0f}".format(
    P([r['land'] for r in rows], .25), P([r['land'] for r in rows], .5), P([r['land'] for r in rows], .75), P([r['land'] for r in rows], .9),
    P([r['prio'] for r in rows], .5), P([r['tip'] for r in rows], .5), P([r['cu'] for r in rows], .5), P([r['cul'] for r in rows], .5)))
print("  tip paths:", ", ".join(f"{k}:{c}" for k, c in collections.Counter(r["tiplab"] for r in rows).most_common(8)))
print(f"  corr(size, land) {corr(sz, [r['land'] for r in rows]):+.2f}   corr(land, pnl%) {corr([r['land'] for r in rows], [r['pnl_pct'] for r in rows]):+.2f}"
      f"   corr(dev, land) {corr([r['dev'] for r in rows if 'dev' in r], [r['land'] for r in rows if 'dev' in r]):+.2f}")
wp = [r for r in rows if r.get("dslot") is not None]
if wp:
    print(f"POSITION (on {len(wp)} labelled launches)  same slot {sum(r['dslot'] == 0 for r in wp) / len(wp) * 100:.0f}%"
          f"  pos q25 {P([r['pos'] for r in wp if r['pos'] is not None], .25)} med {P([r['pos'] for r in wp if r['pos'] is not None], .5)} q75 {P([r['pos'] for r in wp if r['pos'] is not None], .75)}")
    for lo, hi in ((0, 0.01), (0.01, 0.03), (0.03, 0.06), (0.06, 9)):
        g = [r for r in wp if lo <= r["land"] < hi]
        if g:
            pp = [r["pos"] for r in g if r["pos"] is not None]
            print(f"  land {lo:.2f}-{hi:.2f} n={len(g):3} same-slot {sum(r['dslot'] == 0 for r in g) / len(g) * 100:3.0f}%  pos med {P(pp, .5) if pp else '-'}")
    for k in ("r2", "cont", "base"):
        g = [r for r in wp if r.get(k)]
        if g:
            print(f"  on {k:4} launches n={len(g):3}  pnl mean {st.mean(r['pnl_pct'] for r in g) * 100:+.1f}% med {st.median(r['pnl_pct'] for r in g) * 100:+.1f}%  win {sum(r['pnl'] > 0 for r in g) / len(g) * 100:.0f}%  size med {P([r['sol'] for r in g], .5):.2f}  dev med {P([r['dev'] for r in g], .5):.2f}  bundle med {P([r['gsol'] for r in g], .5):.2f}")
    print(f"  labelled share of his buys: {len(wp) / n * 100:.0f}% (race data covers 10-18 18:00 -> 10-19 14:33 UTC)")
# exits
ex = [r for r in rows if r["sells"]]
one = [r for r in ex if len(r["sells"]) == 1]
hold = [r["sells"][-1]["dt"] for r in ex]
first = [r["sells"][0] for r in ex]
print(f"EXITS  with sells {len(ex)}/{n}  sold-all-at-once {len(one) / max(1, len(ex)) * 100:.0f}%  sells/trade med {P([len(r['sells']) for r in ex], .5)}"
      f"  first sell dt med {P([s['dt'] for s in first], .5)} s (q25 {P([s['dt'] for s in first], .25)} q75 {P([s['dt'] for s in first], .75)})"
      f"  last sell dt med {P(hold, .5)} s q75 {P(hold, .75)} q90 {P(hold, .9)}")
print(f"  first sell: frac med {P([s['frac'] for s in first], .5):.2f}  price/entry med {P([s['pxr'] for s in first], .5):.3f} (q25 {P([s['pxr'] for s in first], .25):.3f} q75 {P([s['pxr'] for s in first], .75):.3f})"
      f"   sell landing cost med {P([s['land'] for r in ex for s in r['sells']], .5):.5f}")
if one:
    print(f"  all-at-once trades n={len(one)}: hold med {P([r['sells'][0]['dt'] for r in one], .5)} s  px/entry med {P([r['sells'][0]['pxr'] for r in one], .5):.3f}  pnl mean {st.mean(r['pnl_pct'] for r in one) * 100:+.1f}%")
mult = [r for r in ex if len(r["sells"]) > 1]
if mult:
    print(f"  scale-out trades n={len(mult)}: fracs med " + " ".join(f"{P([r['sells'][i]['frac'] for r in mult if len(r['sells']) > i], .5):.2f}" for i in range(4))
          + f"  gaps(s) med " + " ".join(f"{P([r['sells'][i]['dt'] - r['sells'][i - 1]['dt'] for r in mult if len(r['sells']) > i], .5)}" for i in range(1, 4))
          + f"  pnl mean {st.mean(r['pnl_pct'] for r in mult) * 100:+.1f}%")
for lo, hi in ((0, 3), (3, 6), (6, 15), (15, 60), (60, 10 ** 6)):
    g = [r for r in ex if lo <= r["sells"][-1]["dt"] < hi]
    if g:
        print(f"  last sell {lo:>3}-{hi:<7}s n={len(g):4} pnl mean {st.mean(r['pnl_pct'] for r in g) * 100:+.1f}% med {st.median(r['pnl_pct'] for r in g) * 100:+.1f}%")
