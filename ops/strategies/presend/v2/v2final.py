#!/usr/bin/env python3
# PRE-SEND V2 robustness of the finalist configs (read-only): per day, per PKT hour band, worst clock hour, hour-block bootstrap
# (90% interval of SOL per 24 h on TEST and on all days), without the top 1% of fills, the per-fill margin split, per leader client,
# the send rate the stream needs (armed windows overlap: attempts per second; share of armed time above 20 / 50 / 100 per s).
# usage: nice python3 v2final.py  -> presend_v2/v2final.json + .txt   (finalists = FINAL below)
import sys, os, json, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
import v2eng as E
import v2run as R
OUT = f"{V.OUT}/v2final"
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
FINAL = json.load(open(f"{V.OUT}/finalists.json"))
PUMP_FEE = 0.0125
rng = np.random.default_rng(11)

def rate_needs(o, k):
    """attempt rate over time from the armed intervals (k per 212 ms per armed window)"""
    a0 = o["arm_a0"]; a1 = o["arm_a1"]
    if len(a0) == 0: return {}
    ev = np.concatenate([np.stack([a0, np.ones(len(a0))], 1), np.stack([a1, -np.ones(len(a1))], 1)])
    ev = ev[np.lexsort((ev[:, 1], ev[:, 0]))]
    conc = np.cumsum(ev[:, 1]); dt = np.diff(ev[:, 0], append=ev[-1, 0])
    busy = dt[conc > 0].sum()
    rate = conc * k / 0.212
    out = dict(armed_share=float(busy / max(ev[-1, 0] - ev[0, 0], 1)), mean_rate_armed=float((rate * dt)[conc > 0].sum() / max(busy, 1e-9)))
    for cap in (20, 40, 50, 100):
        out[f"over{cap}"] = float(dt[rate > cap].sum() / max(busy, 1e-9))
    out["p99_rate"] = float(np.percentile(np.repeat(rate[conc > 0], np.maximum((dt[conc > 0] / 10).astype(int), 1)), 99)) if busy > 0 else 0.0
    out["max_conc"] = int(conc.max())
    return out

def boot(hourly, days_h, n=4000):
    """hour-block bootstrap of SOL per 24 h"""
    x = np.concatenate(hourly); H = sum(days_h)
    if len(x) == 0: return (0, 0)
    s = rng.integers(0, len(x), (n, len(x)))
    v = x[s].sum(1) / H * 24
    return float(np.percentile(v, 5)), float(np.percentile(v, 95))

if __name__ == "__main__":
    R.G["DD"] = {d: E.load(d) for d in V.DAYS}
    res = {}
    for name, cfg in FINAL.items():
        r = R.ev(cfg, V.DAYS, detail=True)
        k = E.KROW[cfg["row"]]
        say(f"\n=== {name}: {json.dumps(cfg)}")
        rows = {}
        for d in V.DAYS:
            o = r[d]; h = R.G["DD"][d]["hours"]
            g = o["acc_gross"]; nf = o["fill"]
            rows[d] = dict(per24=o["per24"], fills=nf, armed=o["armed"], fill_rate=o["fill_rate"], per_fill=o["per_fill"], gross_fill=o["gross_per_fill"],
                           att_fill=o["att_per_fill"], att_cost_fill=o["cost_att"] / max(nf, 1), winr=o["winr"])
            say(f"  {d} ({h:4.1f} h): {o['per24']:+6.2f} SOL/24h | fills {nf} ({nf / h * 24:.0f}/24h) of {o['armed']} armed ({100 * o['fill_rate']:.1f}%) | per fill: "
                f"after pump fees {o['gross_per_fill']:+.4f} - fixed {E.COST[cfg.get('cost', 'real')]['fill']:.4f} - attempts {o['cost_att'] / max(nf, 1):.4f} = net {o['per_fill']:+.4f} "
                f"| win {100 * o['winr']:.0f}% | att/fill {o['att_per_fill']:.0f}")
        # hour bands (PKT) over TEST days and all days
        hb = collections.defaultdict(lambda: [0.0, 0.0]); hb_all = collections.defaultdict(lambda: [0.0, 0.0])
        hours_test = []; hours_all = []; worst = []
        for d in V.DAYS:
            o = r[d]; hr = o["hourly"]; t0 = V.pk(V.WIN[d][0])
            hours_all.append(hr)
            if d in R.TEST: hours_test.append(hr)
            for i, v in enumerate(hr):
                hh = ((t0 + i * 3600 + 5 * 3600) // 3600) % 24
                hb_all[hh][0] += v; hb_all[hh][1] += 1
                if d in R.TEST: hb[hh][0] += v; hb[hh][1] += 1
                worst.append((v, d, V.pkt(t0 + i * 3600)))
        say("  PKT hour bands (sum over all 4 days, SOL; [hours]): " + " ".join(f"{h:02d}:{hb_all[h][0]:+.2f}[{hb_all[h][1]}]" for h in sorted(hb_all)))
        bands = {"00-06": range(0, 6), "06-12": range(6, 12), "12-18": range(12, 18), "18-24": range(18, 24)}
        bb = {}
        for bn, hs in bands.items():
            v = sum(hb_all[h][0] for h in hs); n = sum(hb_all[h][1] for h in hs)
            vt = sum(hb[h][0] for h in hs); nt = sum(hb[h][1] for h in hs)
            bb[bn] = dict(all=v / max(n, 1) * 24, all_h=n, test=vt / max(nt, 1) * 24, test_h=nt)
        say("  band SOL/24h (all days | test days): " + " | ".join(f"{bn} {x['all']:+.2f} ({x['all_h']} h) | {x['test']:+.2f} ({x['test_h']} h)" for bn, x in bb.items()))
        worst.sort()
        tc = sum(1 for v, d, _ in worst if d in R.TEST); pos_t = sum(1 for v, d, _ in worst if d in R.TEST and v > 0)
        say(f"  worst clock hours: " + ", ".join(f"{d} {t} {v:+.3f}" for v, d, t in worst[:4]) + f" | positive hours on TEST {pos_t}/{tc} ({100 * pos_t / max(tc, 1):.0f}%)")
        ci_t = boot(hours_test, [R.G["DD"][d]["hours"] for d in R.TEST]); ci_a = boot(hours_all, [R.G["DD"][d]["hours"] for d in V.DAYS])
        tot_t = sum(r[d]["pnl"] for d in R.TEST) / sum(R.G["DD"][d]["hours"] for d in R.TEST) * 24
        tot_a = sum(r[d]["pnl"] for d in V.DAYS) / sum(R.G["DD"][d]["hours"] for d in V.DAYS) * 24
        say(f"  SOL/24h TEST {tot_t:+.2f} [90% {ci_t[0]:+.2f}, {ci_t[1]:+.2f}] | ALL 4 days {tot_a:+.2f} [{ci_a[0]:+.2f}, {ci_a[1]:+.2f}]")
        # without the top 1% of fills (TEST)
        nets = np.concatenate([r[d]["acc_net"] for d in R.TEST]); costs_att = sum(r[d]["cost_att"] for d in R.TEST)
        if len(nets):
            top = np.sort(nets)[::-1][: max(1, int(len(nets) * 0.01))]
            say(f"  TEST without the top 1% of fills ({len(top)}): {(nets.sum() - top.sum() - costs_att) / sum(R.G['DD'][d]['hours'] for d in R.TEST) * 24:+.2f}/24h "
                f"(top 1% carry {top.sum():+.2f} of {nets.sum() - costs_att:+.2f} SOL)")
        # per leader client of the entry slot (R2-R4)
        pc = collections.defaultdict(list)
        for d in ("R2", "R3", "R4"):
            o = r[d]; D = R.G["DD"][d]
            ci = D["f_f"][o["acc_fr"], E.FFI["cls_in"]].astype(int)
            for c, v in zip(ci.tolist(), o["acc_net"].tolist()): pc[V.CLS[c]].append(v)
        say("  per leader client of the entry slot (R2-R4; fill net before attempt costs): " + " | ".join(f"{c} {len(v)} fills {np.mean(v):+.4f}/fill" for c, v in sorted(pc.items(), key=lambda kv: -len(kv[1]))))
        # rate needs (all days)
        rn = {d: rate_needs(r[d], k) for d in V.DAYS}
        say("  send rate needed (k {:g}/slot): ".format(k) + " | ".join(f"{d}: armed {100 * x['armed_share']:.0f}% of the time, mean {x['mean_rate_armed']:.0f}/s while armed, "
                                                           f">20/s {100 * x['over20']:.0f}%, >50/s {100 * x['over50']:.0f}%, >100/s {100 * x['over100']:.0f}%, max {x['max_conc']} windows"
                                                           for d, x in rn.items() if x))
        res[name] = dict(cfg=cfg, days=rows, bands=bb, ci_test=ci_t, ci_all=ci_a, test24=tot_t, all24=tot_a, rate=rn, pos_hours_test=(pos_t, tc),
                         worst=[(v, d, t) for v, d, t in worst[:6]], per_client={c: (len(v), float(np.mean(v))) for c, v in pc.items()})
    json.dump(res, open(OUT + ".json", "w"), default=float)
    open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")
