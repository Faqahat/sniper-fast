#!/usr/bin/env python3
"""GAP step 5 (read-only): 10-27 18:00-22:00 PKT zoom. haqq lots by bucket and by hour; our wallets' txs (episodes) and the
AMS r28 engine (18:21-22:03, 0.50 SOL pre-send, QUIET on) by hour: dumps logged, M2 picks, fires, pre-send arms/skips/fills.
Out: gap/g5_evening.txt"""
import pickle, collections, sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/gap")
from g3_ledger import grp
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
T0 = 1793106000; T1 = T0 + 4 * 3600          # 10-27 18:00 -> 22:00 PKT (13:00 -> 17:00 UTC)
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    assert L.pkt(T0) == "10-27 18:00", L.pkt(T0)
    Z = pickle.load(open(f"{OUT}/g3_rows.pkl", "rb")); rows = Z["rows"]; eps = Z["eps"]
    RUNS = pickle.load(open(f"{OUT}/g2_engine.pkl", "rb"))
    R = [r for r in rows if T0 <= r["b"]["bt"] < T1]
    for E in eps:
        bk = [rows[i]["bucket"] for i in E["his"]]
        E["cat"] = "f" if "f" in bk else ("e" if (bk and not E["fill"]) else ("d" if E["fill"] else ("x" if E["n_fail"] > 0 else "o")))
    Ew = [E for E in eps if T0 <= E["bt"] < T1]
    n = len(R); net = sum(r["net"] for r in R)
    P(f"# 10-27 18:00-22:00 PKT: haqq {n:,} lots, net {net:+.2f} SOL (MEASURED lot view), SOL in {sum(r['size'] for r in R):.0f}; "
      f"ours {sum(E['pnl'] for E in Ew):+.3f} SOL over {len(Ew)} episodes (MEASURED wallet)")
    P("\n## haqq by bucket")
    P("| bucket | detail | lots | his net | win % | SOL in |"); P("|---|---|---|---|---|---|")
    g = collections.defaultdict(list)
    for r in R:
        det = r["reason"] if r["bucket"] != "c" else grp(r["reason"]) + " | " + r["reason"]
        g[(r["bucket"], det)].append(r)
    for (bk, det), v in sorted(g.items(), key=lambda kv: ("NOCOV a b c e f".split().index(kv[0][0]), -sum(r["net"] for r in kv[1]))):
        P(f"| {bk} | {det} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * np.mean([r['net'] > 0 for r in v]):.0f} | {sum(r['size'] for r in v):.0f} |")
    P("\n## per hour: haqq vs ours")
    P("| hour PKT | his lots | his net | his DIP net | his ADD net | his e+f net | our episodes | our P&L | our fills | our pre-send fills P&L | our fail-only P&L |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    for h in range(4):
        a, b = T0 + h * 3600, T0 + (h + 1) * 3600
        V = [r for r in R if a <= r["b"]["bt"] < b]; E2 = [E for E in Ew if a <= E["bt"] < b]
        P(f"| {L.pkt(a)} | {len(V)} | {sum(r['net'] for r in V):+.2f} | {sum(r['net'] for r in V if r['type'] == 'DIP'):+.2f} | {sum(r['net'] for r in V if r['type'] == 'ADD'):+.2f} | "
          f"{sum(r['net'] for r in V if r['bucket'] in ('e', 'f')):+.2f} | {len(E2)} | {sum(E['pnl'] for E in E2):+.3f} | {sum(E['fill'] for E in E2)} | "
          f"{sum(E['pnl'] for E in E2 if E['fill'] and E['path'] == 'ps'):+.3f} | {sum(E['pnl'] for E in E2 if not E['fill']):+.3f} |")
    P("\n## our episodes by category (MEASURED)")
    c = collections.defaultdict(list)
    for E in Ew: c[(E["cat"], E["path"])].append(E)
    P("| category | path | episodes | P&L | fills | failed attempts | his lots linked | his net on linked |"); P("|---|---|---|---|---|---|---|---|")
    for k, v in sorted(c.items()):
        hl = [rows[i] for E in v for i in E["his"]]
        P(f"| {k[0]} | {k[1]} | {len(v)} | {sum(E['pnl'] for E in v):+.3f} | {sum(E['n_ok'] for E in v)} | {sum(E['n_fail'] for E in v)} | {len(hl)} | {sum(r['net'] for r in hl):+.2f} |")
    # engine view AMS28
    X = RUNS["AMS28"]
    P(f"\n## AMS r28 engine log (MEASURED): {L.pkt(X['start'])} -> {L.pkt(X['end'])}")
    dumps = [(k, v) for k, vv in X["dumps"].items() for v in vv]
    pas = sum(1 for k, v in dumps if v[2]); m2 = sum(1 for k, v in dumps if v[3])
    P(f"dumps logged {len(dumps):,}, picked (pass) {pas}, fired {len(X['fire'])}; pick skips {collections.Counter(X['skip'].values()).most_common()}")
    P(f"pre-send: arms {len(X['arms'])} (disarm whys {collections.Counter(a[5] for a in X['arms']).most_common()}), skips {collections.Counter(s[3] for s in X['pskips']).most_common()}, "
      f"attempts landed {len(X['patt'])} ({collections.Counter(p[4] for p in X['patt']).most_common()}), fills {len(X['pfills'])}")
    # his DIP lots in the r28 window: did the dumper trigger pre-send arms / skips?
    ids, idm = L.ids_map()
    W = [r for r in R if X["start"] <= r["b"]["bt"] <= X["end"] and r["type"] == "DIP"]
    arm_w = collections.defaultdict(list); sk_w = collections.defaultdict(list)
    for a in X["arms"]: arm_w[(a[0], a[1])].append(a)
    for s in X["pskips"]: sk_w[(s[0], s[1])].append(s)
    cnt = collections.defaultdict(list)
    for r in W:
        b = r["b"]; sel = ids[b["d_user"]] if b.get("d_user") is not None else None
        a = arm_w.get((b["mint"], sel)); s = sk_w.get((b["mint"], sel))
        whale = (b.get("d_bal_pct") or 0) >= 6
        k = ("armed on this dumper" if a else "skipped: " + s[-1][3] if s else "dumper >= 6% holder, no trigger" if whale else "dumper < 6% holder")
        cnt[k].append(r)
    P(f"\nhis DIP lots inside the r28 window ({len(W)}), by pre-send status of the DUMPER (MEASURED):")
    P("| pre-send status of the dumper | his lots | his net | win % | bucket mix |"); P("|---|---|---|---|---|")
    for k, v in sorted(cnt.items(), key=lambda kv: -sum(r["net"] for r in kv[1])):
        P(f"| {k} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * np.mean([r['net'] > 0 for r in v]):.0f} | {dict(collections.Counter(r['bucket'] for r in v))} |")
    # dumper type and size for his DIP lots in the window
    P("\nhis DIP lots in 18:00-22:00 by dumper type (MEASURED):")
    P("| dumper | lots | his net | win % | median dump SOL | median drop % |"); P("|---|---|---|---|---|---|")
    dt = collections.defaultdict(list)
    for r in R:
        if r["type"] == "DIP": dt[r["b"]["d_type"]].append(r)
    for k, v in sorted(dt.items(), key=lambda kv: -sum(r["net"] for r in kv[1])):
        P(f"| {k} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * np.mean([r['net'] > 0 for r in v]):.0f} | {np.median([r['b']['d_sol'] for r in v]):.2f} | {100 * np.median([r['b']['d_drop'] for r in v]):.1f} |")
    # top tokens of his in the window
    P("\nhis top 10 tokens in the window (MEASURED):")
    P("| mint | lots | buys types | his net | buckets |"); P("|---|---|---|---|---|")
    tm = collections.defaultdict(list)
    for r in R: tm[r["b"]["mint"]].append(r)
    for m, v in sorted(tm.items(), key=lambda kv: -sum(r["net"] for r in kv[1]))[:10]:
        P(f"| {m[:10]} | {len(v)} | {dict(collections.Counter(r['type'] for r in v))} | {sum(r['net'] for r in v):+.3f} | {dict(collections.Counter(r['bucket'] for r in v))} |")
    P("\nhis bottom 5 tokens in the window:")
    for m, v in sorted(tm.items(), key=lambda kv: sum(r["net"] for r in kv[1]))[:5]:
        P(f"| {m[:10]} | {len(v)} | {dict(collections.Counter(r['type'] for r in v))} | {sum(r['net'] for r in v):+.3f} | {dict(collections.Counter(r['bucket'] for r in v))} |")
    # tokens: multi-lot vs single-lot positions in the window
    one = [v for v in tm.values() if len(v) == 1]; multi = [v for v in tm.values() if len(v) > 1]
    P(f"\ntokens with 1 lot: {len(one)}, net {sum(r['net'] for v in one for r in v):+.2f}; tokens with 2+ lots: {len(multi)}, net {sum(r['net'] for v in multi for r in v):+.2f} (MEASURED)")
    open(f"{OUT}/g5_evening.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
