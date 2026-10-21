# READ-ONLY (host, no RPC): 4yFAz round trips from txs.jsonl -> per-mint trade rows (trades_rows.json) + activity/PnL tables.
# PnL per trade = sells*(1-fee) - buys*(1+fee) - tx fees (base+priority) of its buy/sell txs - tips (system transfers from
# the wallet to anyone else). ATA rent is excluded (reclaimed by the close txs). Failed-tx fees are a wallet-level cost.
# usage: python3 trades.py <txs.jsonl> <sigs.json> <tipmap.json> [failed_sample.jsonl]
import sys, json, statistics, collections, time
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
R = [json.loads(l) for l in open(sys.argv[1])]; SIGS = json.load(open(sys.argv[2])); TM = json.load(open(sys.argv[3]))
FS = [json.loads(l) for l in open(sys.argv[4])] if len(sys.argv) > 4 else []


def route(dst):
    if dst in TM: return TM[dst]
    if dst.lower().startswith("b1oom"): return "b1oom?"
    if dst.startswith(("noz", "TEMPa")): return "nozomi"
    if dst.startswith("moon"): return "lunar"
    return "other:" + dst[:6]


by = collections.defaultdict(lambda: dict(buys=[], sells=[]))
for r in R:
    mine = [t for t in r["trades"] if t["user"] == W]
    if not mine or r["err"]: continue
    tips = [(d, l) for s, d, l in r["transfers"] if s == W and d != W]
    for t in mine:
        f = ((t.get("fee") or 95) + (t.get("cfee") or 30)) / 1e4
        x = dict(sig=r["sig"], slot=r["slot"], bt=r["bt"], tidx=r.get("tidx"), sol=t["sol"] / 1e9, tok=t["tok"], f=f, vsol=t["vsol"], vtok=t["vtok"],
                 txfee=r["fee"] / 1e9 / len(mine), tip=sum(l for _, l in tips) / 1e9 / len(mine), routes=[route(d) for d, _ in tips],
                 cul=r["cul"], cup=r["cup"], cu=r["cu"], prog=[p[:6] for p in r["progs"] if p[:6] not in ("111111", "Comput")], nix=r["nix"])
        by[t["mint"]]["buys" if t["buy"] else "sells"].append(x)

rows = []
for m, d in by.items():
    b, s = d["buys"], d["sells"]
    if not b: continue          # sells of positions opened before the window
    b.sort(key=lambda x: (x["slot"], x["tidx"] or 0)); s.sort(key=lambda x: (x["slot"], x["tidx"] or 0))
    bin_ = sum(x["sol"] * (1 + x["f"]) for x in b); sout = sum(x["sol"] * (1 - x["f"]) for x in s)
    cost = sum(x["txfee"] + x["tip"] for x in b + s)
    tb, ts = sum(x["tok"] for x in b), sum(x["tok"] for x in s)
    closed = ts >= 0.999 * tb
    rows.append(dict(mint=m, slot=b[0]["slot"], bt=b[0]["bt"], n_buys=len(b), n_sells=len(s), sol_in=bin_, sol_out=sout, cost=cost,
                     pnl=sout - bin_ - cost, ret=(sout - bin_ - cost) / bin_, closed=closed,
                     hold_s=(s[-1]["bt"] - b[0]["bt"]) if s else None, hold_slots=(s[-1]["slot"] - b[0]["slot"]) if s else None,
                     first_sell_slots=(s[0]["slot"] - b[0]["slot"]) if s else None, first_sell_s=(s[0]["bt"] - b[0]["bt"]) if s else None,
                     buy0=b[0], buy_px=(b[0]["vsol"] - b[0]["sol"] * 1e9) / (b[0]["vtok"] + b[0]["tok"]),
                     sells=[dict(slot=x["slot"], bt=x["bt"], sol=x["sol"], tok_frac=x["tok"] / tb if tb else None) for x in s],
                     sell_cost=sum(x["txfee"] + x["tip"] for x in s), buy_cost=sum(x["txfee"] + x["tip"] for x in b)))
rows.sort(key=lambda r: r["slot"])
json.dump(rows, open("trades_rows.json", "w"))

t0 = min(r["bt"] for r in SIGS if r["bt"]); t1 = max(r["bt"] for r in SIGS if r["bt"])
H = (t1 - t0) / 3600
cl = [r for r in rows if r["closed"]]
print(f"window {time.strftime('%m-%d %H:%M', time.gmtime(t0))} .. {time.strftime('%m-%d %H:%M', time.gmtime(t1))} UTC = {H:.1f} h; sigs {len(SIGS)}, ok {sum(not r['err'] for r in SIGS)}, failed {sum(r['err'] for r in SIGS)}")
print(f"mints bought {len(rows)} ({len(rows)/H:.2f}/h), closed {len(cl)}, open/partial {len(rows)-len(cl)}")
pn = [r["pnl"] for r in cl]; sz = [r["sol_in"] for r in cl]
q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]
print(f"size SOL: median {statistics.median(sz):.2f} p10 {q(sz,.1):.2f} p90 {q(sz,.9):.2f} max {max(sz):.2f}; total in {sum(sz):.1f}")
print(f"PnL (closed, ex failed-tx fees): total {sum(pn):+.2f} SOL, mean {statistics.mean(pn):+.4f}, median {statistics.median(pn):+.4f}, "
      f"win {sum(p>0 for p in pn)/len(pn):.0%}, return on SOL in {sum(pn)/sum(sz):+.2%}")
print(f"  without best 3: {sum(sorted(pn)[:-3]):+.2f}; best {sorted(pn)[-5:]}, worst {sorted(pn)[:5]}")
hs = [r["hold_s"] for r in cl if r["hold_s"] is not None]; hsl = [r["hold_slots"] for r in cl]
print(f"hold: median {statistics.median(hs)} s ({statistics.median(hsl)} slots), p90 {q(hs,.9)} s, max {max(hs)} s; first sell median {statistics.median([r['first_sell_slots'] for r in cl])} slots")
print("sells per trade:", sorted(collections.Counter(r["n_sells"] for r in cl).items()), " buys per trade:", sorted(collections.Counter(r["n_buys"] for r in cl).items()))
fee_ok = sum(r["cost"] for r in rows)
# failed tx fees: sample mean fee x number failed
nf = sum(r["err"] for r in SIGS)
ff = statistics.mean([x["fee"] for x in FS]) / 1e9 if FS else None
print(f"costs inside trades (tx fees + tips): {fee_ok:.3f} SOL; failed txs {nf} x mean fee {ff} = {nf*ff if ff else float('nan'):.3f} SOL")
print("\nper UTC day/hour block:")
days = collections.defaultdict(list)
for r in cl: days[time.strftime("%m-%d", time.gmtime(r["bt"]))].append(r)
for d, xs in sorted(days.items()):
    print(f"  {d}: trades {len(xs)}, in {sum(x['sol_in'] for x in xs):.1f}, pnl {sum(x['pnl'] for x in xs):+.2f}, win {sum(x['pnl']>0 for x in xs)/len(xs):.0%}")
hr = collections.Counter(time.strftime("%m-%d %H", time.gmtime(r["bt"])) for r in rows)
print("  buys per hour:", " ".join(f"{k[-5:]}:{v}" for k, v in sorted(hr.items())))
for lab, a, b_ in (("last 24 h", t1 - 86400, t1), ("24-48 h ago", t1 - 2 * 86400, t1 - 86400), ("last 6 h", t1 - 6 * 3600, t1)):
    xs = [r for r in cl if a <= r["bt"] < b_]
    if xs:
        nfx = sum(1 for s in SIGS if s["err"] and s["bt"] and a <= s["bt"] < b_)
        print(f"{lab}: trades {len(xs)} ({len(xs)/((b_-a)/3600):.2f}/h), in {sum(x['sol_in'] for x in xs):.1f}, pnl {sum(x['pnl'] for x in xs):+.2f}"
              f" (minus failed fees ~{nfx*ff if ff else 0:.2f}), mean {statistics.mean([x['pnl'] for x in xs]):+.3f}, win {sum(x['pnl']>0 for x in xs)/len(xs):.0%}")
print("\nbuy tx settings: cu limit", collections.Counter(r["buy0"]["cul"] for r in rows).most_common(6))
cp = [r["buy0"]["cup"] or 0 for r in rows]
print("  cu price (uL) median", statistics.median(cp), "p90", q(cp, .9), "; prio SOL median", statistics.median([r["buy0"]["txfee"] for r in rows]), "p90", q([r["buy0"]["txfee"] for r in rows], .9))
print("  tip SOL median", statistics.median([r["buy0"]["tip"] for r in rows]), "p90", q([r["buy0"]["tip"] for r in rows], .9))
print("  routes on landed buy tx:", collections.Counter(tuple(r["buy0"]["routes"]) for r in rows).most_common(12))
print("  buy program:", collections.Counter(tuple(r["buy0"]["prog"]) for r in rows).most_common(5))
sp = collections.Counter(tuple(x for s in by[r["mint"]]["sells"] for x in s["prog"]) [:3] for r in rows)
print("  sell programs:", sp.most_common(5))
