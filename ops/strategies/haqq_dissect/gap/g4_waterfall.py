#!/usr/bin/env python3
"""GAP step 4 (read-only): our side per day + shared-trade decomposition + the waterfall haqq -> us, from g3_rows.pkl.
Episode category (ours): f = linked to a haqq lot in bucket f (both filled); e = linked only to e lots and we never filled;
  d = we filled, no haqq lot on our fill's event; x = no fill, no haqq lot (failed fires / pre-send tries = pure cost); o = other
  (sell/close-only leftovers). Day of an episode = day of its first tx.
Shared (f) decomposition per episode (his linked f lots vs our episode):
  size   = (his SOL in - our SOL in) x his curve return per SOL
  return = our SOL in x (his curve return per SOL - our curve return per SOL)     (entry price + exit timing)
  costs  = (our tx costs incl. failed attempts and rent net) - his tx costs
Out: gap/g4_ours.txt, gap/g4_waterfall.txt, gap/g4.json"""
import pickle, collections, json, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/gap")
from g3_ledger import grp
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"


def boot_sum(v, n=2000, seed=7):
    v = np.asarray(v, float)
    if not len(v): return (0.0, 0.0)
    r = np.random.default_rng(seed); s = v[r.integers(0, len(v), (n, len(v)))].sum(1)
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


def main():
    Z = pickle.load(open(f"{OUT}/g3_rows.pkl", "rb")); rows = Z["rows"]; eps = Z["eps"]; meta = Z["meta"]
    for E in eps:
        bk = [rows[i]["bucket"] for i in E["his"]]
        E["cat"] = "f" if "f" in bk else ("e" if (bk and not E["fill"]) else ("d" if E["fill"] else ("x" if E["n_fail"] > 0 else "o")))
        if bk and "f" not in bk and E["fill"]: E["cat"] = "d"            # filled on another dump; his lot there was an e
    days = sorted(set(r["day"] for r in rows) | set(E["day"] for E in eps))
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); out.append(s)
    # ---------------- our side
    P("# Our side per day (MEASURED wallet SOL change of every FRA/AMS tx, fees+tips+rent; episodes per wallet+mint)")
    P("| day | total | f: both filled | d: our fill, no haqq lot | e: our fail, he filled | x: fail/tries, no haqq lot | o: other | regular (fills / fail-only) | pre-send (fills / fail-only) |")
    P("|---|---|---|---|---|---|---|---|---|")
    J = {}
    for d in days:
        V = [E for E in eps if E["day"] == d]
        c = collections.defaultdict(float); n = collections.Counter()
        for E in V: c[E["cat"]] += E["pnl"]; n[E["cat"]] += 1
        pr = collections.defaultdict(float); pn = collections.Counter()
        for E in V:
            k = ("reg" if E["path"] in ("reg", "unk") else "ps" if E["path"] == "ps" else "mixed") + ("_F" if E["fill"] else "_X")
            pr[k] += E["pnl"]; pn[k] += 1
        tot = sum(E["pnl"] for E in V)
        J[d] = dict(ours=tot, **{f"o_{k}": v for k, v in c.items()}, **{f"on_{k}": v for k, v in n.items()}, **{f"p_{k}": v for k, v in pr.items()})
        P(f"| {L.day_name(d)} | {tot:+.3f} | {c['f']:+.3f} ({n['f']}) | {c['d']:+.3f} ({n['d']}) | {c['e']:+.3f} ({n['e']}) | {c['x']:+.3f} ({n['x']}) | {c['o']:+.3f} ({n['o']}) | "
          f"{pr['reg_F']:+.3f} ({pn['reg_F']}) / {pr['reg_X']:+.3f} ({pn['reg_X']}) | {pr['ps_F']:+.3f} ({pn['ps_F']}) / {pr['ps_X']:+.3f} ({pn['ps_X']}) |"
          + (f" mixed {pr['mixed_F'] + pr['mixed_X']:+.3f}" if pn['mixed_F'] + pn['mixed_X'] else ""))
    # ---------------- e / f detail: path and error of our matched attempts
    P("\n# Shared events: haqq lots where we landed a buy attempt after the same dump (MEASURED), by our path and failure code")
    P("| day | bucket | our path | his lots | his net | his win % | our attempts ok / 6042 guard / 6001 deadline / other | slots after dump p50 |")
    P("|---|---|---|---|---|---|---|---|")
    for d in days:
        for bk in ("e", "f"):
            g = collections.defaultdict(list)
            for r in rows:
                if r["day"] != d or r["bucket"] != bk: continue
                paths = set(a[2] for a in r["m_att"]); pth = "pre-send" if paths == {"ps"} else "regular" if paths <= {"reg", "unk", None} else "both"
                g[pth].append(r)
            for pth, v in sorted(g.items()):
                at = [a for r in v for a in r["m_att"]]
                cc = collections.Counter("ok" if a[0] == "buy_ok" else a[1] for a in at)
                P(f"| {d} | {bk} | {pth} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * np.mean([r['net'] > 0 for r in v]):.0f} | "
                  f"{cc['ok']} / {cc['6042']} / {cc['6001']} / {sum(cc.values()) - cc['ok'] - cc['6042'] - cc['6001']} | {np.median([a[4] for a in at]):.0f} |")
    # ---------------- f decomposition
    P("\n# Both filled (f): his lots vs our episode on the same event (MEASURED curve P&L; costs MEASURED for us, his MEASURED from 10-25 19:20)")
    P("| day | events | his lots | his SOL in | our SOL in | his net | our net | gap | of which size | return (entry+exit) | costs | his ret/SOL | our ret/SOL |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    FD = {}
    for d in days:
        V = [E for E in eps if E["day"] == d and E["cat"] == "f"]
        s = collections.defaultdict(float); nl = 0
        for E in V:
            hl = [rows[i] for i in E["his"] if rows[i]["bucket"] == "f"]; nl += len(hl)
            hs = sum(r["size"] for r in hl); hg = sum(r["b"]["gross"] for r in hl); ht = sum(r["b"]["txc"] for r in hl); hn = sum(r["net"] for r in hl)
            os_ = E["size"]; og = E["gross"]; on = E["pnl"]; oc = og - on
            hr = hg / hs if hs else 0.0; orr = og / os_ if os_ else 0.0
            s["hs"] += hs; s["os"] += os_; s["hn"] += hn; s["on"] += on; s["size"] += (hs - os_) * hr; s["ret"] += os_ * (hr - orr); s["cost"] += oc - ht
            s["hg"] += hg; s["og"] += og
        FD[d] = dict(s)
        if V:
            P(f"| {L.day_name(d)} | {len(V)} | {nl} | {s['hs']:.1f} | {s['os']:.1f} | {s['hn']:+.3f} | {s['on']:+.3f} | {s['hn'] - s['on']:+.3f} | {s['size']:+.3f} | {s['ret']:+.3f} | {s['cost']:+.3f} | "
              f"{100 * s['hg'] / max(s['hs'], 1e-9):+.2f}% | {100 * s['og'] / max(s['os'], 1e-9):+.2f}% |")
    open(f"{OUT}/g4_ours.txt", "w").write("\n".join(out) + "\n")
    # ---------------- waterfall
    out2 = []
    def Q(*a):
        s = " ".join(str(x) for x in a); print(s); out2.append(s)
    Q("\n# Waterfall per day: haqq lot-view net -> our wallet P&L. Every row MEASURED (tape lots / wallet txs) except where marked.")
    Q("# Read: haqq net - (each bucket he earned and we did not) - (shared-trade gap) + (our fills he skipped) + (our costs) = our P&L")
    W = {}
    for d in days:
        R = [r for r in rows if r["day"] == d]; Ed = [E for E in eps if E["day"] == d]
        X = sum(r["net"] for r in R)
        lines = []
        def add(name, v, n=None, note=""):
            lines.append((name, v, n, note))
        cnt = lambda f: [r for r in R if f(r)]
        nc = cnt(lambda r: r["bucket"] == "NOCOV"); add("tape hour not usable (NOCOV)", -sum(r["net"] for r in nc), len(nc))
        a = cnt(lambda r: r["bucket"] == "a"); add("a. run gaps (no trading engine)", -sum(r["net"] for r in a), len(a))
        for t in ("ADD", "DIP_LATE", "DEAD", "LAUNCH", "MOMO", "OTHER", "PROBE"):
            v = cnt(lambda r, t=t: r["bucket"] == "b" and r["reason"] == t); add(f"b. type {t}", -sum(r["net"] for r in v), len(v))
        cg = collections.defaultdict(list)
        for r in R:
            if r["bucket"] == "c": cg[grp(r["reason"])].append(r)
        for k in ("gate refused (M2/IMIT1)", "near-only (far leader)", "one-position busy", "QUIET skip", "pre-send not armed", "dump below thresholds",
                  "token too old", "cooldown/fee budget", "other"):
            v = cg.get(k, []); add(f"c. {k}", -sum(r["net"] for r in v), len(v))
        e = cnt(lambda r: r["bucket"] == "e"); add("e. guard failures: his P&L where we fired and failed", -sum(r["net"] for r in e), len(e))
        fd = FD.get(d, {})
        f_l = cnt(lambda r: r["bucket"] == "f")
        f_his = sum(r["net"] for r in f_l); f_ep_his = fd.get("hn", 0.0)
        add("f. shared: his net on f lots not in a same-day f episode", -(f_his - f_ep_his), None, "(boundary/matching residue)")
        add("f. shared: size (he buys more SOL)", -fd.get("size", 0.0))
        add("f. shared: return per SOL (entry + exit)", -fd.get("ret", 0.0))
        add("f. shared: tx costs (ours incl. failed attempts - his)", -fd.get("cost", 0.0))
        dd = [E for E in Ed if E["cat"] == "d"]; add("+ d. our fills where he had no lot", sum(E["pnl"] for E in dd), len(dd))
        ee = [E for E in Ed if E["cat"] == "e"]; add("+ e. our cost of the failed fires (he filled)", sum(E["pnl"] for E in ee), len(ee))
        xx = [E for E in Ed if E["cat"] == "x"]; add("+ x. failed fires / pre-send tries, no haqq lot (cost)", sum(E["pnl"] for E in xx), len(xx))
        oo = [E for E in Ed if E["cat"] == "o"]; add("+ o. other our txs (sells/closes outside episodes)", sum(E["pnl"] for E in oo), len(oo))
        Y = sum(E["pnl"] for E in Ed)
        resid = X + sum(v for _, v, _, _ in lines) - Y
        Q(f"\n## {L.day_name(d)}: haqq {X:+.2f} -> ours {Y:+.3f}  (gap {X - Y:+.2f}; check residual {resid:+.4f})")
        Q("| step | SOL | lots / episodes | running |"); Q("|---|---|---|---|")
        run = X; Q(f"| haqq net (all his lots bought this day) | {X:+.2f} | {len(R):,} | {run:+.2f} |")
        for name, v, n, note in lines:
            run += v
            if abs(v) < 0.005 and not n: continue
            Q(f"| {name} {note} | {v:+.2f} | {'' if n is None else f'{n:,}'} | {run:+.2f} |")
        Q(f"| = our wallet P&L | {Y:+.3f} | {len(Ed):,} | |")
        W[d] = dict(X=X, Y=Y, resid=resid, lines=[(nm, v, n) for nm, v, n, _ in lines])
    open(f"{OUT}/g4_waterfall.txt", "w").write("\n".join(out2) + "\n")
    json.dump(dict(W=W, J=J, FD=FD), open(f"{OUT}/g4.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
