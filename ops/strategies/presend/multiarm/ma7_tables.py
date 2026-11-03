#!/usr/bin/env python3
"""MULTIARM step 7: tables from the joint replay runs (ma6_run): every variant vs the base (R0 = the live dip26 rule), per run.
Per rep, windows are matched to the base's by key (T2: its live window id; re-arm: the dump (mint, slot, idx, j); chained: new):
  extra     = windows the variant arms that the base does not (their fills = the extra trades)
  knock-on  = the change on the base's own windows (one-position pauses, rate caps, deferrals, supersedes, blocked T2 triggers)
  net       = variant total - base total (= extra + knock-on)
Cash = slip basis (follower adjustment); raw = all followers kept; -20% = slip + 20% of the remaining follower buys dropped.
Per day = x 24 / the run's evaluated hours. CI: block bootstrap over the run's hours (90%, 10,000 draws) of the rep-mean hourly net.
w/o top 5 = net minus the 5 best extra windows (per rep). Day = 08:00-19:59 PKT, night = 20:00-07:59 PKT.
usage: ma7_tables.py RUNDIR OUT.json [--base R0] [--variants a,b,c]"""
import sys, os, glob, json, pickle, collections, argparse
import numpy as np


def load(rundir):
    V = collections.defaultdict(dict)
    for f in sorted(glob.glob(f"{rundir}/*.pkl")):
        d = pickle.load(open(f, "rb"))
        V[d["name"]][d["rep"]] = d
    return V


def key_of(r):
    k = r["key"]
    return tuple(k) if isinstance(k, (list, tuple)) else (k,)


def hour_of(t_ms, t0): return int((t_ms - t0) // 3.6e6)


def pkt_hour(t_ms): return int(((t_ms / 1e3 + 5 * 3600) // 3600) % 24)


def summarize(V, base, name, boot=10000, seed=7):
    reps = sorted(set(V[name]) & set(V[base]))
    if not reps: return None
    m0 = V[base][reps[0]]["meta"]; hours = m0["hours"]; t0 = m0["t_start"]
    nh = int(np.ceil(hours))
    day = 24.0 / hours
    S = collections.defaultdict(list)
    hourly = np.zeros((len(reps), nh)); hourly_cut = np.zeros((len(reps), nh)); hourly_raw = np.zeros((len(reps), nh))
    pkt = np.array([pkt_hour(t0 + (h + 0.5) * 3.6e6) for h in range(nh)])
    hw = np.array([min(1.0, hours - h) for h in range(nh)])
    tok_counts = []
    for ri, rep in enumerate(reps):
        A = V[name][rep]["rows"]; B = V[base][rep]["rows"]
        bk = {key_of(r): r for r in B}; ak = {key_of(r): r for r in A}
        extra = [r for k, r in ak.items() if k not in bk]
        common = [(r, bk[k]) for k, r in ak.items() if k in bk]
        gone = [r for k, r in bk.items() if k not in ak]
        tot = lambda rows, f: sum(r[f] for r in rows)
        S["windows"].append(len(A)); S["windows_base"].append(len(B))
        S["re_windows"].append(sum(1 for r in A if r["kind"] == "rearm")); S["re_windows_base"].append(sum(1 for r in B if r["kind"] == "rearm"))
        S["fills"].append(tot(A, "filled")); S["fills_base"].append(tot(B, "filled"))
        S["extra_windows"].append(len(extra)); S["gone_windows"].append(len(gone))
        S["extra_fills"].append(tot(extra, "filled"))
        afill = {k for k, r in ak.items() if r["filled"]}; bfill = {k for k, r in bk.items() if r["filled"]}
        S["fills_removed"].append(len(bfill - afill)); S["fills_added"].append(len(afill - bfill))
        for f, lab in (("cash", ""), ("cash_cut", "_cut"), ("cash_naive", "_raw")):
            S["net" + lab].append(tot(A, f) - tot(B, f))
            S["extra" + lab].append(tot(extra, f))
            S["knock" + lab].append(sum(a[f] - b[f] for a, b in common) - tot(gone, f))
            S["total" + lab].append(tot(A, f)); S["total_base" + lab].append(tot(B, f))
            S["re_total" + lab].append(sum(r[f] for r in A if r["kind"] == "rearm"))
        # general: the net without its 5 best window-level contributions (extra windows +cash, gone windows -cash, common windows the change)
        for f, lab in (("cash", ""), ("cash_cut", "_cut")):
            contrib = [r[f] for r in extra] + [-r[f] for r in gone] + [a[f] - b[f] for a, b in common]
            best = sorted((x for x in contrib if x > 0), reverse=True)[:5]
            S["net_wo_best5" + lab].append(S["net" + lab][-1] - sum(best))
        top = sorted((r["cash"] for r in extra), reverse=True)[:5]
        S["net_wo_top5"].append(S["net"][-1] - sum(x for x in top if x > 0))
        topc = sorted((r["cash_cut"] for r in extra), reverse=True)[:5]
        S["net_cut_wo_top5"].append(S["net_cut"][-1] - sum(x for x in topc if x > 0))
        S["fails"].append(tot(A, "fails")); S["fails_base"].append(tot(B, "fails"))
        S["ticks"].append(tot(A, "ticks")); S["refused"].append(tot(A, "refused")); S["paused"].append(tot(A, "paused"))
        S["extra_fill_cash"].append(sum(r["cash"] for r in extra if r["filled"]))
        S["extra_fill_n"].append(sum(1 for r in extra if r["filled"]))
        S["double_pos"].append(V[name][rep]["meta"]["stats"].get("double_position", 0))
        for r in A:
            h = hour_of(r["t_arm"], t0)
            if 0 <= h < nh: hourly[ri, h] += r["cash"]; hourly_cut[ri, h] += r["cash_cut"]; hourly_raw[ri, h] += r["cash_naive"]
        for r in B:
            h = hour_of(r["t_arm"], t0)
            if 0 <= h < nh: hourly[ri, h] -= r["cash"]; hourly_cut[ri, h] -= r["cash_cut"]; hourly_raw[ri, h] -= r["cash_naive"]
        tc = collections.Counter(r["mint"] for r in A if r["filled"])
        tok_counts.append(list(tc.values()))
    mean = lambda k: float(np.mean(S[k]))
    hm = hourly.mean(0); hc = hourly_cut.mean(0); hr = hourly_raw.mean(0)
    rng = np.random.default_rng(seed)
    def ci(h):
        idx = rng.integers(0, nh, size=(boot, nh))
        tot_ = h[idx].sum(1) / hw[idx].sum(1) * 24.0
        return [round(float(np.percentile(tot_, 5)), 2), round(float(np.percentile(tot_, 95)), 2)]
    dmask = (pkt >= 8) & (pkt < 20)
    def part(mask, h):
        if hw[mask].sum() < 0.5: return None
        return round(float(h[mask].sum() / hw[mask].sum() * 24.0), 2)
    allc = [c for tc in tok_counts for c in tc]
    out = {"variant": name, "reps": len(reps), "hours": round(hours, 2),
           "re_windows_day": round(mean("re_windows") * day, 0), "extra_windows_day": round((mean("re_windows") - mean("re_windows_base")) * day, 0),
           "extra_windows_matched_day": round(mean("extra_windows") * day, 0), "fills_day": round(mean("fills") * day, 1),
           "extra_fills_day": round((mean("fills") - mean("fills_base")) * day, 1), "extra_window_fills_day": round(mean("extra_fills") * day, 1),
           "trades_per_token": {"median": float(np.median(allc)) if allc else None, "p90": float(np.percentile(allc, 90)) if allc else None,
                                "max_mean": float(np.mean([max(tc) if tc else 0 for tc in tok_counts])), "max": int(max(allc)) if allc else None,
                                "share_3plus": round(float(np.mean([c >= 3 for c in allc])), 4) if allc else None, "tokens_day": round(len(allc) / len(reps) * day, 1)},
           "net_day": round(mean("net") * day, 2), "net_day_rep_range": [round(min(S["net"]) * day, 2), round(max(S["net"]) * day, 2)],
           "extra_day": round(mean("extra") * day, 2), "knock_day": round(mean("knock") * day, 2),
           "net_cut_day": round(mean("net_cut") * day, 2), "extra_cut_day": round(mean("extra_cut") * day, 2),
           "net_raw_day": round(mean("net_raw") * day, 2),
           "net_wo_top5_day": round(mean("net_wo_top5") * day, 2), "net_cut_wo_top5_day": round(mean("net_cut_wo_top5") * day, 2),
           "net_wo_best5_day": round(mean("net_wo_best5") * day, 2), "net_cut_wo_best5_day": round(mean("net_wo_best5_cut") * day, 2),
           "gone_windows_day": round(mean("gone_windows") * day, 0),
           "fills_removed": round(mean("fills_removed"), 1), "fills_added": round(mean("fills_added"), 1),
           "net_sol": round(mean("net"), 3), "net_cut_sol": round(mean("net_cut"), 3), "net_wo_best5_sol": round(mean("net_wo_best5"), 3),
           "net_cut_wo_best5_sol": round(mean("net_wo_best5_cut"), 3), "total_sol": round(mean("total"), 3), "total_cut_sol": round(mean("total_cut"), 3),
           "fills": round(mean("fills"), 1), "net_sol_rep_range": [round(min(S["net"]), 3), round(max(S["net"]), 3)],
           "ci90_net_day": ci(hm), "ci90_net_cut_day": ci(hc),
           "day_net_day": part(dmask, hm), "night_net_day": part(~dmask, hm), "day_net_cut_day": part(dmask, hc), "night_net_cut_day": part(~dmask, hc),
           "hours_positive_share": round(float(np.mean(hm[hw > 0.5] > 1e-9)), 3), "hours_n": int((hw > 0.5).sum()),
           "total_day": round(mean("total") * day, 2), "total_base_day": round(mean("total_base") * day, 2), "re_total_day": round(mean("re_total") * day, 2),
           "total_cut_day": round(mean("total_cut") * day, 2), "re_total_cut_day": round(mean("re_total_cut") * day, 2),
           "fail_fees_day": round(mean("fails") * 5120 / 1e9 * day, 3), "extra_fail_fees_day": round((mean("fails") - mean("fails_base")) * 5120 / 1e9 * day, 3),
           "refused_share": round(mean("refused") / max(mean("ticks"), 1), 4), "paused_share": round(mean("paused") / max(mean("ticks"), 1), 4),
           "extra_fill_mSOL_each": round(1e3 * float(np.sum(S["extra_fill_cash"]) / max(np.sum(S["extra_fill_n"]), 1)), 2),
           "double_positions": mean("double_pos"),
           "hourly_net": [round(float(x), 4) for x in hm], "hourly_pkt": pkt.tolist(), "hourly_w": hw.tolist()}
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("rundir"); ap.add_argument("out"); ap.add_argument("--base", default="R0"); ap.add_argument("--variants", default=None)
    a = ap.parse_args()
    V = load(a.rundir)
    names = a.variants.split(",") if a.variants else sorted(V)
    res = {}
    for n in names:
        if n not in V: continue
        s = summarize(V, a.base, n)
        if s: res[n] = s
    json.dump(res, open(a.out, "w"), indent=1)
    cols = ("re_windows_day", "extra_windows_day", "extra_fills_day", "net_day", "extra_day", "knock_day", "net_cut_day", "net_wo_top5_day", "ci90_net_day", "day_net_day",
            "night_net_day", "fail_fees_day", "refused_share")
    print("variant".ljust(10), " ".join(c[:14].rjust(14) for c in cols), "trades/token")
    for n, s in res.items():
        tp = s["trades_per_token"]
        print(n.ljust(10), " ".join(str(s[c]).rjust(14) for c in cols), f"{tp['median']}/{tp['p90']}/{tp['max']} 3+ {tp['share_3plus']}")


if __name__ == "__main__":
    main()
