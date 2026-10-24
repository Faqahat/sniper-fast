#!/usr/bin/env python3
# Selection study, step 1 (local only): what do the three dip bots buy? For every dump (sel_events.jsonl.gz) the label = which
# target wallets bought right after it (first buy within 1000 ms, before the next big sell). Per wallet: how many dumps it
# bought, its delay, and per feature the middle-90% range of its buys vs all dumps, the share of all dumps inside that range,
# and its buy rate inside vs outside (the "watch envelope"). Also: how OUR replay does on the dumps each wallet bought
# (guarded, 4-slot exit, proxy 35/50/75 ms) vs all dumps.
import json, gzip, collections, statistics, time, sys
EV = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/sel/sel_events.jsonl.gz", "rt")]
W8 = ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX")
def F(r):
    x = r["xf"]; t = r["tok"]
    return dict(age=r["age"], sell=r["sell"], drop_pct=round((1 - r["drop"]) * 100, 2), vsol=r["vsol"], pb=r["pb"], dd=r["dd"], nb=r["nb"], ns=r["ns"],
                b20=r["b20"], s20=r["s20"], u20=r["u20"], dev=r["dev"], glued=r["glued"], first_big=int(r["first_big"]), ins=int(r["ins"]),
                s_frac=x["s_frac"], s_pnl=x["s_pnl"], s_nb=x["s_nb"], s_entry=x["s_entry"], n_big=x["n_big"], since_big=x["since_big"], ret5=x["ret5"],
                ret20=x["ret20"], peak_mult=x["peak_mult"], b3=x["b3"], nb3=x["nb3"], sellers20=x["sellers20"], uniq_buyers=x["uniq_buyers"],
                ins_sold=x["ins_sold"], net_flow=x["net_flow"], slotpos=x["slotpos"], prev_sell_ms=r["prev_sell_ms"], n_tr=t["n_tr"], vmax=t["vmax"],
                since_buy=t["since_buy"])
def g(r, L, H="4"):
    # our guarded P&L at proxy L: the buy happens only if the price when we land is <= 1.02 x the post-dump price
    if str(L) not in r["pnl"]: return None
    return r["pnl"][str(L)][H] if r["px"][str(L)] <= 1.02 else -0.0002
ts = [r["bt"] + r["age"] for r in EV]; span = (max(ts) - min(ts)) / 3600
print(f"dumps {len(EV)} over {span:.1f} h ({time.strftime('%m-%d %H:%M', time.gmtime(min(ts) + 18000))} -> {time.strftime('%m-%d %H:%M', time.gmtime(max(ts) + 18000))} PKT); {len(EV) / span:.0f}/h")
FE = [F(r) for r in EV]
keys = list(FE[0])
for w in W8 + ("ANY",):
    lab = [(w in r["lab"]) if w != "ANY" else bool(r["lab"]) for r in EV]
    n = sum(lab)
    if not n: continue
    d = [r["lab"][w] for r, y in zip(EV, lab) if y and w != "ANY"]
    print(f"\n=== {w}: bought {n} dumps ({n / span:.1f}/h, {n / len(EV):.2%} of all dumps)" + (f"; delay ms p10 {statistics.quantiles(d, n=10)[0]:.0f} median {statistics.median(d):.0f} p90 {statistics.quantiles(d, n=10)[8]:.0f}" if d else ""))
    for L in (35, 50, 75):
        a = [g(r, L) for r, y in zip(EV, lab) if y and g(r, L) is not None]; b = [g(r, L) for r in EV if g(r, L) is not None]
        fa = [x for x in a if x != -0.0002]
        print(f"  our replay at {L} ms on ITS dumps: n {len(a)} total {sum(a):+.2f} mean {statistics.mean(a):+.4f} fills {len(fa) / len(a):.0%} win(of fills) {sum(1 for x in fa if x > 0) / max(len(fa), 1):.0%}"
              f" | on ALL dumps: mean {statistics.mean(b):+.4f} win {sum(1 for x in b if x > 0) / len(b):.0%}")
    print(f"  {'feature':12s} | its buys p5 / p50 / p95        | all dumps p5 / p50 / p95       | dumps inside its p5-p95 | its rate inside / outside")
    rows = []
    for k in keys:
        va = sorted(f[k] for f, y in zip(FE, lab) if y); vb = sorted(f[k] for f in FE)
        q = lambda v, p: v[min(len(v) - 1, int(p * len(v)))]
        lo, hi = q(va, 0.05), q(va, 0.95)
        ins = [(lo <= f[k] <= hi) for f in FE]
        n_in = sum(ins); y_in = sum(1 for i, y in zip(ins, lab) if i and y)
        r_in = y_in / max(n_in, 1); r_out = (n - y_in) / max(len(EV) - n_in, 1)
        rows.append((n_in / len(EV), k, q(va, .05), q(va, .5), q(va, .95), q(vb, .05), q(vb, .5), q(vb, .95), r_in, r_out))
    for share, k, a5, a50, a95, b5, b50, b95, ri, ro in sorted(rows):
        print(f"  {k:12s} | {a5:9.3f} {a50:9.3f} {a95:9.3f} | {b5:9.3f} {b50:9.3f} {b95:9.3f} | {share:6.0%}                  | {ri:6.2%} / {ro:6.2%}")
