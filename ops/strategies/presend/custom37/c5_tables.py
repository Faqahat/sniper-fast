#!/usr/bin/env python3
"""CUSTOM37 step 5: per-knob tables (each knob alone vs the current r37 config), TRAIN (r34 r35 r36 f26 f27 f28) vs TEST (r37),
r37 first / second half, bootstrap 90% CI (windows resampled in (run, PKT hour) blocks), without the top 5 windows, -20% followers,
per-run help / hurt, SOL/day at 0.696. Out: stdout + /home/moiz/sniper-data/custom37/knobs.txt + knobs.json"""
import sys, pickle, json, datetime, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
import c37lib as L

G = pickle.load(open(f"{L.D}/grid.pkl", "rb"))
TRAIN = ["r34", "r35", "r36", "f26", "f27", "f28"]; TEST = ["r37"]
HOURS = {}
for run in G["runs"]:
    X = pickle.load(open(f"{L.D}/win_{run}.pkl", "rb")); m = X["meta"]; HOURS[run] = (m["t1"] - m["t0"]) / 3.6e12
pkt = lambda t_ms: datetime.datetime.fromtimestamp(t_ms / 1e3, datetime.UTC) + datetime.timedelta(hours=5)
OUT = []
def p(s=""): print(s); OUT.append(s)


def rows_of(runs, name, cut=0.0, sel=None):
    """per window: (delta net, delta pos_neg, delta pos_pos, delta fees, delta filled, base filled, knob filled, phantom, block key, run)"""
    R = []
    for run in runs:
        W = G["runs"][run]["wins"]; b = G["runs"][run]["res"]["base"][cut]; k = G["runs"][run]["res"][name][cut]
        for n, w in enumerate(W):
            if sel is not None and not sel(w): continue
            dn = (k[n, 1] + k[n, 2]) - (b[n, 1] + b[n, 2])
            R.append((dn, k[n, 4] - b[n, 4], k[n, 3] - b[n, 3], k[n, 2] - b[n, 2], k[n, 0] - b[n, 0], b[n, 0], k[n, 0], k[n, 6], (run, pkt(w["t"]).strftime("%m%d%H")), run))
    return R


def stats(R, seed=7):
    if not R: return None
    d = np.array([r[0] for r in R]) / 1e9
    blocks = {}
    for i, r in enumerate(R): blocks.setdefault(r[8], []).append(i)
    keys = list(blocks); rng = np.random.default_rng(seed); bs = []
    for _ in range(2000):
        pick = rng.integers(0, len(keys), len(keys))
        bs.append(sum(d[blocks[keys[q]]].sum() for q in pick))
    top5 = np.sort(d)[::-1][:5].sum()
    df = np.array([r[4] for r in R])
    ph = np.array([r[7] for r in R])
    infer = float(np.abs(d[ph > 0]).sum() / max(np.abs(d).sum(), 1e-12))
    return {"dnet": d.sum(), "dloss": sum(r[1] for r in R) / 1e9, "dwin": sum(r[2] for r in R) / 1e9, "dfees": sum(r[3] for r in R) / 1e9,
            "added": df[df > 0].sum(), "lost": -df[df < 0].sum(), "ci": np.percentile(bs, [5, 95]), "no_top5": d.sum() - top5, "infer": infer, "n": len(R)}


def hours(runs): return sum(HOURS[r] for r in runs)


if __name__ == "__main__":
    names = [n for n in G["cfgs"] if n != "base"]
    p(f"hours: " + ", ".join(f"{r} {HOURS[r]:.1f}" for r in G["runs"]) + f" | TRAIN {hours(TRAIN):.1f} h, TEST {hours(TEST):.1f} h")
    for runs, lab in ((TRAIN, "TRAIN"), (TEST, "TEST r37")):
        bnet = sum((G["runs"][r]["res"]["base"][0.0][:, 1].sum() + G["runs"][r]["res"]["base"][0.0][:, 2].sum()) for r in runs) / 1e9
        bf = sum(G["runs"][r]["res"]["base"][0.0][:, 0].sum() for r in runs)
        bl = sum(G["runs"][r]["res"]["base"][0.0][:, 4].sum() for r in runs) / 1e9
        bw = sum(G["runs"][r]["res"]["base"][0.0][:, 3].sum() for r in runs) / 1e9
        bfee = sum(G["runs"][r]["res"]["base"][0.0][:, 2].sum() for r in runs) / 1e9
        p(f"{lab} BASE (r37 config, replayed): windows {sum(len(G['runs'][r]['wins']) for r in runs)} fills {bf:.0f} net {bnet:+.3f} SOL "
          f"(winners {bw:+.3f}, losers {bl:+.3f}, failed-try fees {bfee:+.3f}) = {bnet / hours(runs) * 24:+.2f} SOL/day")
    t37 = [w["t"] for w in G["runs"]["r37"]["wins"]]; mid = (min(t37) + max(t37)) / 2
    p(f"r37 halves split at {pkt(mid):%H:%M} PKT")
    p("")
    p("| knob | TRAIN dnet | /day | -20% | CI90 | w/o top5 | TEST r37 dnet | /day | -20% | CI90 | w/o top5 | r37 1st | r37 2nd | dloss | dwinners | dfees | fills +/- | INFERRED share | runs + / - |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    J = {}
    for name in names:
        a = stats(rows_of(TRAIN, name)); a20 = stats(rows_of(TRAIN, name, 0.2))
        b = stats(rows_of(TEST, name)); b20 = stats(rows_of(TEST, name, 0.2))
        h1 = stats(rows_of(TEST, name, sel=lambda w: w["t"] < mid)); h2 = stats(rows_of(TEST, name, sel=lambda w: w["t"] >= mid))
        per = {r: stats(rows_of([r], name))["dnet"] for r in TRAIN + TEST}
        npos = sum(1 for v in per.values() if v > 0.001); nneg = sum(1 for v in per.values() if v < -0.001)
        J[name] = {"train": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in a.items()}, "train20": a20["dnet"], "test": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in b.items()},
                   "test20": b20["dnet"], "h1": h1["dnet"], "h2": h2["dnet"], "per_run": per}
        p(f"| {name} | {a['dnet']:+.3f} | {a['dnet'] / hours(TRAIN) * 24:+.2f} | {a20['dnet']:+.3f} | [{a['ci'][0]:+.2f},{a['ci'][1]:+.2f}] | {a['no_top5']:+.3f} | "
          f"{b['dnet']:+.3f} | {b['dnet'] / hours(TEST) * 24:+.2f} | {b20['dnet']:+.3f} | [{b['ci'][0]:+.2f},{b['ci'][1]:+.2f}] | {b['no_top5']:+.3f} | {h1['dnet']:+.3f} | {h2['dnet']:+.3f} | "
          f"{b['dloss']:+.3f} | {b['dwin']:+.3f} | {b['dfees']:+.3f} | +{b['added']:.1f}/-{b['lost']:.1f} | {b['infer']:.0%} | {npos}/{nneg} |")
    open(f"{L.D}/knobs.txt", "w").write("\n".join(OUT) + "\n")
    json.dump(J, open(f"{L.D}/knobs.json", "w"))
