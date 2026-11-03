#!/usr/bin/env python3
"""QUIET4 step 7: what QUIET and the age-1 skip SAVED in r37: the paper number (ops/obs/filter_savings.py: shadow row c net_cheap of the
skipped triggers, scaled to 0.696 / the shadow's sol_in, failed tries not counted) against the calibrated replay model (virtual windows,
phantom tries, one-position pauses, stop 5:2, failed tries counted; also at -20% followers). Also row c against LIVE on the armed
windows (how far the paper is off where the truth is known). saved = minus the skipped windows' P&L. Per PKT hour and total.
Out: /home/moiz/sniper-data/presend_quiet4/rowc.json + stdout (markdown)"""
import json, pickle, collections, datetime
D4 = "/home/moiz/sniper-data/presend_quiet4"
FN = f"{D4}/runs/dip_ams_r37.jsonl"; LIVE = 0.696


def pkt(t_ns): return datetime.datetime.fromtimestamp(t_ns / 1e9, datetime.UTC) + datetime.timedelta(hours=5)


def main():
    arm_w, exit_c, size_c = {}, {}, {}
    for line in open(FN, errors="replace"):
        if '"ev":"presend_' not in line: continue
        d = json.loads(line); e = d["ev"]
        if e == "presend_arm": arm_w[d["sig"]] = d.get("w")
        elif e == "presend_exit" and d.get("row") == "c": exit_c[d["w"]] = d.get("net_cheap", d.get("pnl", 0.0))
        elif e == "presend_fill" and d.get("row", "c") == "c" and "entry" in d: size_c.setdefault(d.get("w"), d["entry"].get("sol_in", 0) / 1e9)
    X = pickle.load(open(f"{D4}/win_r37.pkl", "rb")); V = pickle.load(open(f"{D4}/values_r37.pkl", "rb"))
    agg = collections.defaultdict(lambda: collections.defaultdict(float)); hourly = collections.defaultdict(lambda: collections.defaultdict(float))
    for W in X["wins"]:
        k = f"{W['ses']}:{W['w']}"; kind = W["kind"]
        if kind == "blocked": continue
        sw = arm_w.get(W["trig"]["sig"]); rc = None
        if sw is not None and sw in exit_c: rc = exit_c[sw] * (LIVE / size_c[sw] if size_c.get(sw) else 1.0)
        if kind == "armed":
            if k not in V["live"]: continue
            mv, mf = V["live"][k]; mc = mv + V["armed"][k][((5, 2), 0.2)][0] - V["armed"][k][((5, 2), 0.0)][0]
            mv_nofee = (W["pnl_real"] or 0.0)
        else:
            if k not in V["virt"]: continue
            mv, mf = V["virt"][k][((5, 2), 0.0)]; mc = V["virt"][k][((5, 2), 0.2)][0]; mv_nofee = None
        a = agg[kind]; h = hourly[(kind, pkt(W["trig"]["t"]).strftime("%m-%d %H"))]
        for x in (a, h):
            x["n"] += 1; x["matched"] += sw is not None
            if rc is not None: x["rc_f"] += 1; x["rc_w"] += rc > 0; x["rc"] += rc
            x["m"] += mv; x["mf"] += mf; x["mc"] += mc
            if kind == "armed":
                x["live_f"] += 1 if W["fills"] else 0; x["live_w"] += 1 if (W["fills"] and (W["pnl_real"] or 0) > 0) else 0; x["live_real"] += W["pnl_real"] or 0.0
                if rc is not None and W["fills"]: x["both_f"] += 1; x["both_rc"] += rc; x["both_live"] += W["pnl_real"] or 0.0
    out = []
    def pr(s=""): out.append(s); print(s)
    pr("| skip | triggers | paper row c: would-fill (W/L) | paper row c SAVED | model fills | model SAVED (incl. failed tries) | model SAVED at -20% followers |\n|---|---|---|---|---|---|---|")
    for kind, nm in (("quiet", "QUIET arm rule"), ("young", "age-1 skip (min age 2)")):
        a = agg[kind]
        pr(f"| {nm} | {a['n']:.0f} | {a['rc_f']:.0f} ({a['rc_w']:.0f}/{a['rc_f'] - a['rc_w']:.0f}) | {-a['rc']:+.3f} | {a['mf']:.1f} | {-a['m']:+.3f} | {-a['mc']:+.3f} |")
    a = agg["armed"]
    pr(f"\nrow c on the ARMED windows (truth known): {a['n']:.0f} windows; row-c would-fill {a['rc_f']:.0f} ({a['rc_w']:.0f} W), row-c P&L {a['rc']:+.3f} | live fills {a['live_f']:.0f} "
       f"({a['live_w']:.0f} W), live realized {a['live_real']:+.3f}, live value incl. failed tries {a['m']:+.3f} | on the {a['both_f']:.0f} windows both filled: row c {a['both_rc']:+.3f} vs live {a['both_live']:+.3f}")
    pr("\nper PKT hour: QUIET saved (paper row c | model) and age-1 saved (paper row c | model); cumulative in brackets")
    pr("| hour (PKT) | QUIET skips | QUIET row c | QUIET model | age-1 skips | age-1 row c | age-1 model |\n|---|---|---|---|---|---|---|")
    hrs = sorted({h for (_, h) in hourly})
    cq = cqm = cy = cym = 0.0
    for h in hrs:
        q = hourly.get(("quiet", h), {}); y = hourly.get(("young", h), {})
        cq += -q.get("rc", 0); cqm += -q.get("m", 0); cy += -y.get("rc", 0); cym += -y.get("m", 0)
        pr(f"| {h} | {q.get('n', 0):.0f} | {-q.get('rc', 0):+.3f} ({cq:+.2f}) | {-q.get('m', 0):+.3f} ({cqm:+.2f}) | {y.get('n', 0):.0f} | {-y.get('rc', 0):+.3f} ({cy:+.2f}) | {-y.get('m', 0):+.3f} ({cym:+.2f}) |")
    json.dump({"agg": {k: dict(v) for k, v in agg.items()}, "hourly": {f"{k[0]}|{k[1]}": dict(v) for k, v in hourly.items()}}, open(f"{D4}/rowc.json", "w"))
    open(f"{D4}/rowc_out.md", "w").write("\n".join(out))


if __name__ == "__main__":
    main()
