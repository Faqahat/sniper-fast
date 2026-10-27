#!/usr/bin/env python3
"""REAL replay: the variant tables from variants_<tag>_raw.pkl (per variant: SOL/day, both halves, per PKT day, fills/day,
failed-try cost per fill, P&L per fill; the null's 95th percentile; pass / fail per the pre-registered rules).
usage: vreport.py TAG [TAG ...]"""
import sys, os, pickle, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib
OUT = "/home/moiz/sniper-data/presend_real"

def day_hours():
    H = json.load(open(f"{OUT}/hours.json"))
    c = collections.Counter(rlib.pkt(x["t0"], "%m-%d") for x in H["test"])
    return {k: v / 6.0 for k, v in c.items()}

def table(tags):
    DH = day_hours()
    R = {}; meta = None
    for tag in tags:
        X = pickle.load(open(f"{OUT}/variants_{tag}_raw.pkl", "rb"))
        meta = X
        for k, v in X["R"].items(): R[(tag,) + k] = v
    hours = meta["hours"]; hh = meta["half_hours"]
    rows = []
    nulls = {}
    for key, lst in R.items():
        tag, name, kind = key
        if kind != "null": continue
        vals = [sum(r[3] for r in rows_) / 1e9 / hours * 24 for seed, rows_ in lst]
        nulls[(tag, name)] = (float(np.percentile(vals, 95)), float(np.mean(vals)), len(vals))
    out = []
    for key, lst in sorted(R.items()):
        tag, name, kind = key
        if kind != "main": continue
        per = []
        for seed, rs in lst:
            tot = sum(r[3] for r in rs) / 1e9
            d = collections.defaultdict(float)
            for r in rs: d[rlib.pkt(r[1], "%m-%d")] += r[3] / 1e9
            fills = sum(r[2] for r in rs)
            per.append(dict(day=tot / hours * 24, h1=sum(r[3] for r in rs if r[0] == 1) / 1e9 / hh[1] * 24, h2=sum(r[3] for r in rs if r[0] == 2) / 1e9 / hh[2] * 24,
                            fills_day=fills / hours * 24, armed_day=len(rs) / hours * 24, fee_fill=(sum(r[5] for r in rs) / 1e9 / fills if fills else np.nan),
                            pnl_fill=(sum(r[4] for r in rs) / 1e9 / fills if fills else np.nan), win=(sum(1 for r in rs if r[2] and r[4] > 0) / fills if fills else np.nan),
                            perday={k: v / DH[k] * 24 for k, v in d.items()}, sent=sum(r[6] for r in rs) / hours * 24, landed=sum(r[7] for r in rs) / hours * 24,
                            refused=sum(r[8] for r in rs) / hours * 24, tries_fill=(sum(r[7] for r in rs) / fills if fills else np.nan)))
        m = {k: float(np.nanmean([p[k] for p in per])) for k in per[0] if k != "perday"}
        days = sorted(DH)
        m["perday"] = {k: float(np.mean([p["perday"].get(k, 0.0) for p in per])) for k in days}
        m["sd_day"] = float(np.std([p["day"] for p in per]))
        nl = nulls.get((tag, name))
        m["null95"] = nl[0] if nl else None
        m["passes"] = bool(m["h1"] > 0 and m["h2"] > 0 and (nl is None or m["day"] > nl[0]))
        m["name"] = name; m["tag"] = tag; m["draws"] = len(per)
        out.append(m)
    return out, nulls, DH

if __name__ == "__main__":
    out, nulls, DH = table(sys.argv[1:])
    days = sorted(DH)
    print("variant            SOL/day   half1   half2 | fills/d armed/d | fail-fee/fill  pnl/fill  win%  landed/fill | " + " ".join(days) + " | null95")
    for m in out:
        print("%-16s %+7.2f %+7.2f %+7.2f | %6.1f %6.0f | %.4f %+.4f %4.0f%% %6.0f | %s | %s" % (
            m["tag"][:6] + ":" + m["name"], m["day"], m["h1"], m["h2"], m["fills_day"], m["armed_day"], m["fee_fill"], m["pnl_fill"], 100 * m["win"], m["tries_fill"],
            " ".join("%+6.2f" % m["perday"][d] for d in days), ("%+.2f" % m["null95"]) if m["null95"] is not None else "-"))
    for k, v in nulls.items(): print("null", k, "p95 %+.2f mean %+.2f (n %d)" % v)
