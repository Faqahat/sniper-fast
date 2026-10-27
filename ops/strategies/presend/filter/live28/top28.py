#!/usr/bin/env python3
"""LIVE28 step 6: per window, what QUIET did (INFERRED from the replay; live MEASURED), for the top misses and saves.
  skipped trigger S_i : effect = live - counterfactual = -(C - A0) over the window itself + the knock-on it causes on live windows
                        of the same token (a live twin the armed trigger would have blocked loses its MEASURED live net)
  stopped window w    : effect = -(D - A0) on the window itself (after the stop)
Prints per window: fill probability, mean net in the counterfactual, P&L if filled, the knock-on, the tape story.
  twins: several skips can share one live twin, so the twin knock-on is counted once per TOKEN (C - A0 over all of the token's
  skipped and live windows) and split evenly over the token's skips; 'kn' (per skip, all same-token live windows) is shown for reference.
usage: top28.py POOL [TAG]"""
import sys, os, pickle, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib28 as L
import effects28 as E
import tables28 as T

RENT = 5020

if __name__ == "__main__":
    pool = sys.argv[1] if len(sys.argv) > 1 else "P3"; tag = sys.argv[2] if len(sys.argv) > 2 else "main"
    Z = pickle.load(open(f"{L.DATA}/replay28_{pool}_{tag}.pkl", "rb"))
    EJ = json.load(open(f"{L.DATA}/effects28_{pool}_{tag}.json"))
    M = Z["meta"]; lv = {x["key"]: x for x in M["live"]}; sk = {x["key"]: x for x in M["skip"]}
    R = L.load_run(); tp = L.Tape28(R)
    Dsk = E.deltas(Z, "C", "A0"); Dst = E.deltas(Z, "D", "A0"); Dto = E.deltas(Z, "B", "A0")
    nd = len(Dsk)
    rows = []
    # skipped triggers: own P&L in C, the knock-on = the C-A0 deltas of live windows on the same mint
    for k, x in sk.items():
        own = np.array([d.get(k, 0.0) for d in Dsk]) / 1e9
        same = [k2 for k2, y in lv.items() if y["mint"] == x["mint"]]
        kn = np.array([sum(d.get(k2, 0.0) for k2 in same) for d in Dsk]) / 1e9
        C = [by[k] for _, by in Z["out"]["C"]]
        pf = np.mean([r["filled"] for r in C]); pnl = [r["pnl"] - RENT for r in C if r["filled"]]
        qs = np.mean([bool(r["q_stop"]) for r in C])
        blk = collections.Counter(k2 for _, by in Z["out"]["C"] for k2 in same if not by[k2]["armed"])
        # exact twin accounting is per TOKEN (several skips can share one live twin): the token's whole C-A0 over its skipped and live
        # windows; the knock-on shown per skip is the token's live part, and the per-skip effect is the token net split evenly by skips
        tok_keys = [k2 for k2, y in sk.items() if y["mint"] == x["mint"]] + same
        tok = np.array([sum(d.get(k2, 0.0) for k2 in tok_keys) for d in Dsk]) / 1e9
        nsk = sum(1 for y in sk.values() if y["mint"] == x["mint"])
        eff = -own.mean() if not same else (-own.mean() if nsk == 1 else None)
        if same and nsk > 1:      # several skips on a twin token: own part + an even share of the token's live knock-on
            eff = -own.mean() - (tok.mean() - sum(np.mean([d.get(k2, 0.0) for d in Dsk]) / 1e9 for k2 in sk if sk[k2]["mint"] == x["mint"])) / nsk
        elif same:
            eff = -tok.mean()
        rows.append(dict(kind="skip", key=k, name=f"S{k[1]}", t=x["t_ns"], mint=x["mint"], phase=x["phase"], pf=pf, own=own.mean(), kn=kn.mean(),
                         eff=eff, tok=(-tok.mean() if same else None), nsk=nsk, pnl=(np.mean(pnl) / 1e9 if pnl else None), qstop=qs, whale=x["whale"], slot=x["slot"], idx=x["idx"],
                         blocked=", ".join(f"w{k2[1]} live {lv[k2]['live']['net'] / 1e9:+.4f} ({v / nd * 100:.0f}%)" for k2, v in blk.items())))
    for k, x in lv.items():
        if x["d_stop"] is None: continue
        own = np.array([d.get(k, 0.0) for d in Dst]) / 1e9
        Dd = [by.get(k) for _, by in Z["out"]["D"]]; Aa = [by[k] for _, by in Z["out"]["A0"]]
        pf = np.mean([bool(a and a["filled"]) for a in Dd]); pfa = np.mean([bool(a["filled"]) for a in Aa])
        pnl = [a["pnl"] - RENT for a in Dd if a and a["filled"]]
        rows.append(dict(kind="stop", key=k, name=f"w{k[1]}", t=x["t_ns"], mint=x["mint"], phase=x["phase"], pf=pf - pfa, own=own.mean(), kn=0.0, eff=-own.mean(),
                         pnl=(np.mean(pnl) / 1e9 if pnl else None), qstop=None, whale=R["W"][k[1]]["arm"]["trig"]["wallet"], slot=x["slot"], idx=x["idx"], blocked=""))
    rows.sort(key=lambda r: r["eff"])
    hdr = "| Window | PKT | Hour | Mint | Fill p | Counterfactual net (own) | Knock-on | **QUIET effect** | P&L if filled | Tape (MEASURED) |\n|---|---|---|---|---|---|---|---|---|---|"
    def line(r):
        st = T.story(tp, r["mint"], r["slot"], r["idx"], r["whale"])
        return (f"| {r['name']} ({r['kind']}) | {L.hm(r['t'])} | {r['phase']} | {r['mint'][:8]} | {r['pf'] * 100:.0f}% | {r['own']:+.4f} | {r['kn']:+.4f}"
                f"{(' [' + r['blocked'] + ']') if r['blocked'] else ''}{(' token net %+.4f over %d skip(s)' % (r['tok'], r['nsk'])) if r.get('tok') is not None else ''} | **{r['eff']:+.4f}** | {r['pnl'] if r['pnl'] is None else format(r['pnl'], '+.4f')} | {st} |")
    print(f"## pool {pool} {tag}: per-window QUIET effect (live - counterfactual; + = QUIET helped)\n")
    print("### Top misses (QUIET cost us: effect < -0.005), worst first\n"); print(hdr)
    for r in rows:
        if r["eff"] < -0.005: print(line(r))
    print("\n### Top saves (effect > +0.005), best first\n"); print(hdr)
    for r in sorted(rows, key=lambda r: -r["eff"]):
        if r["eff"] > 0.005: print(line(r))
    big = [r for r in rows if r["pnl"] is not None and r["pnl"] > 0.03]
    print(f"\n### Windows that would have WON > +0.03 per fill (any fill probability): {len(big)}\n"); print(hdr)
    for r in sorted(big, key=lambda r: r["eff"]): print(line(r))
    small = [r for r in rows if abs(r["eff"]) <= 0.005]
    print(f"\nThe other {len(small)} windows: effect within +-0.005 each, sum {sum(r['eff'] for r in small):+.4f} "
          f"(skipped {sum(1 for r in small if r['kind'] == 'skip')}, stopped {sum(1 for r in small if r['kind'] == 'stop')})")
    print(f"sum over all rows: skip effect {sum(r['eff'] for r in rows if r['kind'] == 'skip'):+.4f} (own {sum(-r['own'] for r in rows if r['kind'] == 'skip'):+.4f}), "
          f"stop {sum(r['eff'] for r in rows if r['kind'] == 'stop'):+.4f}")
    json.dump([{k: (v if not isinstance(v, (np.floating,)) else float(v)) for k, v in r.items() if k != "key"} | {"key": list(r["key"])} for r in rows],
              open(f"{L.DATA}/top28_{pool}_{tag}.json", "w"), indent=1, default=float)
