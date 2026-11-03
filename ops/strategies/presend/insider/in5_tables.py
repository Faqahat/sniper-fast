#!/usr/bin/env python3
"""INSIDER step 5: added SOL/day of every INSIDER variant vs the base (T2 + R0) per run, paired by rep (same seeds per window key).
  net      = variant total - base total (all windows: the insider windows' own P&L + the knock-on on T2 / R0 windows)
  extra    = the insider windows' P&L;  knock = net - extra
  rows     : slip (follower slack) and cut (-20% of the remaining follower buys dropped too); w/o top 1 / top 5 insider windows (per rep)
  hourly   : rep-mean net per run hour (by the window's arm time), PKT hour labels; CI90 = block bootstrap over hours (10,000 draws)
usage: in5_tables.py OUT.json RUN=RUNDIR [RUN=RUNDIR ...]   (the first run is the PICK run; the others are pooled as TEST)"""
import sys, glob, json, pickle, collections
import numpy as np


def load(rundir):
    V = collections.defaultdict(dict)
    for f in sorted(glob.glob(f"{rundir}/*__*.pkl")):
        d = pickle.load(open(f, "rb"))
        V[d["name"]][d["rep"]] = d
    return V


def pkt_hour(t_ms): return int(((t_ms / 1e3 + 5 * 3600) // 3600) % 24)


def per_run(V, name, base="BASE"):
    reps = sorted(set(V[name]) & set(V[base]))
    m0 = V[base][reps[0]]["meta"]; hours = m0["hours"]; t0 = m0["t_start"]
    nh = int(np.ceil(hours))
    H = {f: np.zeros((len(reps), nh)) for f in ("cash", "cash_cut")}
    S = collections.defaultdict(list)
    for ri, rep in enumerate(reps):
        A = V[name][rep]["rows"]; B = V[base][rep]["rows"]
        ins = [r for r in A if r["kind"] == "ins"]
        for f in ("cash", "cash_cut", "cash_naive"):
            net = sum(r[f] for r in A) - sum(r[f] for r in B)
            ext = sum(r[f] for r in ins)
            S["net_" + f].append(net); S["extra_" + f].append(ext); S["knock_" + f].append(net - ext)
            top = sorted((r[f] for r in ins), reverse=True)
            S["wo1_" + f].append(net - sum(x for x in top[:1] if x > 0)); S["wo5_" + f].append(net - sum(x for x in top[:5] if x > 0))
        S["ins_windows"].append(len(ins)); S["ins_fills"].append(sum(r["filled"] for r in ins))
        S["ins_fill_cash"].append(sum(r["cash"] for r in ins if r["filled"]))
        S["ins_fail_fees"].append(sum(r["fails"] for r in ins) * 5120 / 1e9)
        S["base_fills"].append(sum(r["filled"] for r in B)); S["fills"].append(sum(r["filled"] for r in A))
        S["t2_fills"].append(sum(r["filled"] for r in A if r["kind"] == "t2")); S["t2_fills_base"].append(sum(r["filled"] for r in B if r["kind"] == "t2"))
        S["re_fills"].append(sum(r["filled"] for r in A if r["kind"] == "rearm")); S["re_fills_base"].append(sum(r["filled"] for r in B if r["kind"] == "rearm"))
        S["base_total"].append(sum(r["cash"] for r in B)); S["total"].append(sum(r["cash"] for r in A))
        S["ins_end"].append(collections.Counter(r["end_why"] for r in ins))
        S["skips"].append({k: v for k, v in V[name][rep]["meta"]["skips"].items() if k.startswith("ins")})
        S["fee_pause_ms"].append(V[name][rep]["meta"]["fee_pause_ms"]); S["fee_pause_ms_base"].append(V[base][rep]["meta"]["fee_pause_ms"])
        for f in ("cash", "cash_cut"):
            for r in A:
                h = int((r["t_arm"] - t0) // 3.6e6)
                if 0 <= h < nh: H[f][ri, h] += r[f]
            for r in B:
                h = int((r["t_arm"] - t0) // 3.6e6)
                if 0 <= h < nh: H[f][ri, h] -= r[f]
    day = 24.0 / hours
    mean = lambda k: float(np.mean(S[k]))
    hw = np.array([min(1.0, hours - h) for h in range(nh)])
    pkt = [pkt_hour(t0 + (h + 0.5) * 3.6e6) for h in range(nh)]
    ends = collections.Counter()
    for c in S["ins_end"]: ends.update(c)
    sk = collections.Counter()
    for c in S["skips"]: sk.update(c)
    return {"hours": round(hours, 2), "reps": len(reps),
            "added_day": round(mean("net_cash") * day, 2), "added_cut_day": round(mean("net_cash_cut") * day, 2), "added_raw_day": round(mean("net_cash_naive") * day, 2),
            "added_rep_range": [round(min(S["net_cash"]) * day, 2), round(max(S["net_cash"]) * day, 2)],
            "extra_day": round(mean("extra_cash") * day, 2), "knock_day": round(mean("knock_cash") * day, 2),
            "extra_cut_day": round(mean("extra_cash_cut") * day, 2), "knock_cut_day": round(mean("knock_cash_cut") * day, 2),
            "wo1_day": round(mean("wo1_cash") * day, 2), "wo5_day": round(mean("wo5_cash") * day, 2),
            "wo1_cut_day": round(mean("wo1_cash_cut") * day, 2), "wo5_cut_day": round(mean("wo5_cash_cut") * day, 2),
            "ins_windows_day": round(mean("ins_windows") * day, 0), "ins_fills_day": round(mean("ins_fills") * day, 1),
            "ins_mSOL_per_fill": round(1e3 * float(np.sum(S["ins_fill_cash"])) / max(float(np.sum(S["ins_fills"])), 1), 1),
            "ins_fail_fees_day": round(mean("ins_fail_fees") * day, 3),
            "t2_fills_lost_day": round((mean("t2_fills_base") - mean("t2_fills")) * day, 1), "re_fills_lost_day": round((mean("re_fills_base") - mean("re_fills")) * day, 1),
            "base_total_day": round(mean("base_total") * day, 2), "fee_pause_min_day": round(mean("fee_pause_ms") / 6e4 * day, 1),
            "ins_end": {k: round(v / len(reps), 1) for k, v in ends.items()}, "ins_skips": {k: round(v / len(reps), 1) for k, v in sk.items()},
            "_hourly": H["cash"].mean(0).tolist(), "_hourly_cut": H["cash_cut"].mean(0).tolist(), "_hw": hw.tolist(), "_pkt": pkt}


def boot_ci(h, w, n=10000, seed=7):
    h = np.asarray(h); w = np.asarray(w)
    if len(h) == 0: return [None, None]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(h), size=(n, len(h)))
    tot = h[idx].sum(1) / w[idx].sum(1) * 24.0
    return [round(float(np.percentile(tot, 5)), 2), round(float(np.percentile(tot, 95)), 2)]


def main():
    outp = sys.argv[1]
    runs = [a.split("=", 1) for a in sys.argv[2:]]
    data = {r: load(d) for r, d in runs}
    names = sorted(set.intersection(*[set(v) for v in data.values()]) - {"BASE"})
    res = {}
    for n in names:
        res[n] = {}
        for r, _ in runs:
            res[n][r] = per_run(data[r], n)
            x = res[n][r]
            x["ci90_day"] = boot_ci(x["_hourly"], x["_hw"]); x["ci90_cut_day"] = boot_ci(x["_hourly_cut"], x["_hw"])
        test = [r for r, _ in runs[1:]]
        if test:
            hh = sum((res[n][r]["_hourly"] for r in test), []); hc = sum((res[n][r]["_hourly_cut"] for r in test), []); ww = sum((res[n][r]["_hw"] for r in test), [])
            hrs = sum(res[n][r]["hours"] for r in test)
            pool = lambda k: round(sum(res[n][r][k] * res[n][r]["hours"] for r in test) / hrs, 2)
            res[n]["TEST"] = {"hours": round(hrs, 2), "added_day": pool("added_day"), "added_cut_day": pool("added_cut_day"), "wo1_day": pool("wo1_day"),
                              "wo5_day": pool("wo5_day"), "wo5_cut_day": pool("wo5_cut_day"), "extra_day": pool("extra_day"), "knock_day": pool("knock_day"),
                              "ins_fills_day": pool("ins_fills_day"), "ins_windows_day": pool("ins_windows_day"),
                              "ci90_day": boot_ci(hh, ww), "ci90_cut_day": boot_ci(hc, ww), "hours_positive": round(float(np.mean(np.array(hh)[np.array(ww) > 0.5] > 1e-9)), 2)}
    json.dump(res, open(outp, "w"), indent=1)
    pick = runs[0][0]
    cols = ("ins_windows_day", "ins_fills_day", "ins_mSOL_per_fill", "added_day", "extra_day", "knock_day", "added_cut_day", "wo1_day", "wo5_day", "wo5_cut_day", "ci90_day")
    print(f"== {pick} (per day)"); print("variant".ljust(22), " ".join(c[:12].rjust(12) for c in cols))
    for n in names:
        x = res[n][pick]; print(n.ljust(22), " ".join(str(x[c]).rjust(12) for c in cols))


if __name__ == "__main__":
    main()
