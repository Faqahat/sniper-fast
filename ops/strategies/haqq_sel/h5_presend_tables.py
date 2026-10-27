#!/usr/bin/env python3
"""HAQQ_SEL step 5 (read-only): pre-send scenario tables from presend_<pool>.pkl.
Sets: HQ (stream of haqq's tokens only), ALL (stream of every token), NONHQ (the ALL stream's windows NOT on haqq's tokens), HQSPAN
(HQ windows whose trigger is inside haqq's active span +-60 s).
  ideal  : every window alone; chance = an ideal fill exists; P&L = its mean exit P&L; fees = the realistic mean failed-try fees of
           that window (mean over the draws where it armed; stream mean if it never armed)
  50/30% : each chance lands with p (Bernoulli), else only its failed-try fees
  donor  : the realistic replay (sim28, landing donors), per draw; 'cal' = run 28's calibration (wins x 0.81, losses x 1.05)
Ranges: 5-95% of 4000 bootstrap resamples of the windows (with a fresh landing draw / realistic draw per resample).
usage: h5_presend_tables.py [R28|P3]"""
import sys, pickle, json, time
import numpy as np
DATA = "/home/moiz/sniper-data/haqq_sel"
pool = sys.argv[1] if len(sys.argv) > 1 else "R28"
Z = pickle.load(open(f"{DATA}/presend_{pool}.pkl", "rb"))
TOKS = {x["mint"]: x for x in json.load(open(f"{DATA}/tokens.json"))["tokens"]}
W = {tuple(x["key"]): x for x in Z["wins"]}
IDE = Z["ideal"]
rng = np.random.default_rng(11)
NB = 4000
H0 = 1793038500; HALF = H0 + 43200


def real_mat(stream, keys):
    """windows x draws: net, pnl, fees, armed, filled (SOL)"""
    R = Z["real"][stream]; nd = len(R)
    net = np.zeros((len(keys), nd)); pnl = np.zeros_like(net); fee = np.zeros_like(net); arm = np.zeros_like(net); fil = np.zeros_like(net)
    for j, (seed, out) in enumerate(R):
        for i, k in enumerate(keys):
            v = out.get(k)
            if v is None: continue
            arm[i, j], fil[i, j], net[i, j], pnl[i, j], fee[i, j] = v[0], v[1], v[2] / 1e9, v[3] / 1e9, v[4] / 1e9
    return net, pnl, fee, arm, fil


def table(name, stream, keys):
    keys = [k for k in keys if k in IDE]               # QUIET-skipped triggers never arm (not chances)
    net, pnl, fee, arm, fil = real_mat(stream, keys)
    n = len(keys)
    fee_w = np.where(arm.sum(1) > 0, fee.sum(1) / np.maximum(arm.sum(1), 1), np.nan)
    fee_w = np.where(np.isnan(fee_w), np.nanmean(fee_w), fee_w)
    ch = np.array([IDE[k]["chance"] for k in keys]); ip = np.array([IDE[k]["pnl"] for k in keys])
    res = dict(name=name, windows=n, chances=int(ch.sum()), fee_total=float(fee_w.sum()))
    # ideal and partial landing
    for lab, p in (("ideal", 1.0), ("p50", 0.5), ("p30", 0.3)):
        tot = []; fills = []
        for _ in range(NB):
            ix = rng.integers(0, n, n)
            land = ch[ix] & (rng.random(n) < p)
            tot.append(float((ip[ix] * land).sum() - fee_w[ix].sum())); fills.append(int(land.sum()))
        exp = float((ip * ch).sum() * p - fee_w.sum())
        pf = ip[ch]
        res[lab] = dict(fills=float(ch.sum() * p), pnl=exp, lo=float(np.percentile(tot, 5)), hi=float(np.percentile(tot, 95)),
                        pos=float(np.mean(np.array(tot) > 0)), per_chance=float(pf.mean()) if len(pf) else 0.0,
                        win=float(np.mean([IDE[k].get("win", 0) for k in keys if IDE[k]["chance"]])) if ch.any() else 0.0)
    # realistic donor landing
    nd = net.shape[1]
    for lab, f in (("donor", None), ("donor_cal", (0.81, 1.05))):
        if f is None: nn = net
        else: nn = np.where(pnl > 0, pnl * f[0], pnl * f[1]) * fil - fee
        per_draw = nn.sum(0)
        tot = []
        for _ in range(NB):
            ix = rng.integers(0, n, n); jd = rng.integers(0, nd, n)
            tot.append(float(nn[ix, jd].sum()))
        res[lab] = dict(fills=float(fil.sum(0).mean()), armed=float(arm.sum(0).mean()), pnl=float(per_draw.mean()), lo=float(np.percentile(tot, 5)),
                        hi=float(np.percentile(tot, 95)), draws_lo=float(np.percentile(per_draw, 5)), draws_hi=float(np.percentile(per_draw, 95)),
                        pos=float(np.mean(np.array(tot) > 0)), per_fill=float(per_draw.mean() / max(fil.sum(0).mean(), 1e-9)),
                        win=float(((pnl > 0) & (fil > 0)).sum() / max(fil.sum(), 1)))
    # halves (robustness): ideal and donor by 12-h half
    bt = np.array([W[k]["bt"] for k in keys])
    for hl, m in (("h1", bt < HALF), ("h2", bt >= HALF)):
        res[hl] = dict(windows=int(m.sum()), chances=int((ch & m).sum()), ideal=float((ip * ch * m).sum() - (fee_w * m).sum()),
                       donor=float((net * m[:, None]).sum(0).mean()), fills=float((fil * m[:, None]).sum(0).mean()))
    return res


def fmt(r):
    s = [f"### {r['name']}: {r['windows']} armed windows (after QUIET skip), {r['chances']} chances (ideal fill exists), failed-try fees {r['fee_total']:.3f} SOL"]
    s.append("| Scenario | Fills | P&L SOL | 5-95% | P(>0) | Per fill |")
    s.append("|---|---|---|---|---|---|")
    for lab, nm in (("ideal", "(a) ideal: every chance, first in line"), ("p50", "(b) 50% of chances land"), ("p30", "(c) 30% of chances land")):
        x = r[lab]
        s.append(f"| {nm} | {x['fills']:.0f} | {x['pnl']:+.2f} | {x['lo']:+.2f} to {x['hi']:+.2f} | {100 * x['pos']:.0f}% | {x['per_chance']:+.4f} gross |")
    for lab, nm in (("donor", "(d) donor landing (run 28 live tries)"), ("donor_cal", "(d') same, run-28 calibrated")):
        x = r[lab]
        s.append(f"| {nm} | {x['fills']:.0f} | {x['pnl']:+.2f} | {x['lo']:+.2f} to {x['hi']:+.2f} | {100 * x['pos']:.0f}% | {x['per_fill']:+.4f} net |")
    s.append(f"halves (10-26 23:15-10-27 11:15 / 11:15-23:15 PKT): ideal {r['h1']['ideal']:+.2f} / {r['h2']['ideal']:+.2f}; donor {r['h1']['donor']:+.2f} / {r['h2']['donor']:+.2f} "
             f"(windows {r['h1']['windows']} / {r['h2']['windows']}, donor fills {r['h1']['fills']:.0f} / {r['h2']['fills']:.0f})")
    return "\n".join(s)


if __name__ == "__main__":
    keys_all = [k for k in W]
    hq = [k for k in keys_all if W[k]["hq"]]; non = [k for k in keys_all if not W[k]["hq"]]; sp = [k for k in keys_all if W[k]["inspan"]]
    bef = [k for k in hq if TOKS[W[k]["mint"]]["first_slot"] < W[k]["slot"]]; aft = [k for k in hq if TOKS[W[k]["mint"]]["first_slot"] >= W[k]["slot"]]
    out = {}
    for name, stream, keys in (("HQ-KNOWN (haqq had traded the token BEFORE the trigger slot: knowable at arm time)", "HQ", bef),
                               ("HQ-LATER (haqq's first trade on the token at/after the trigger slot: NOT knowable at arm time)", "HQ", aft),("HQ (haqq's tokens only)", "HQ", hq), ("HQSPAN (haqq's tokens, trigger inside his active span +-60 s)", "HQ", sp),
                               ("ALL (every token)", "ALL", keys_all), ("NONHQ (ALL stream, tokens haqq did not trade)", "ALL", non),
                               ("HQ-in-ALL (ALL stream, haqq's tokens)", "ALL", hq),
                               ("NOT-KNOWN (ALL stream minus HQ-KNOWN: what a causal 'haqq traded it before' filter would drop)", "ALL", [k for k in keys_all if k not in set(bef)]),
                               ("HQ-KNOWN-in-ALL (ALL stream, haqq traded it before the trigger)", "ALL", bef)):
        r = table(name, stream, keys); out[name] = r; print(fmt(r)); print()
    json.dump(out, open(f"{DATA}/presend_tables_{pool}.json", "w"), indent=1)
