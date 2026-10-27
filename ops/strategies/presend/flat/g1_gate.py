#!/usr/bin/env python3
"""FLAT study, GATE check (owner request 10-27 ~21:20 PKT; read-only, offline). The post-hoc lead of REPORT §6, now on every live
pre-send run. Rule GATE(M): a try is sent only when the engine had seen >= M OTHER trades since the trigger when it signed it
(the try's pos; others = not the whale, not the run's own wallet: the engine's rule, so FRA's wallet counts as other for AMS and
vice versa). The window stays armed: later tries go out once M is reached. A fill whose try is gated is removed; the window is
then charged the tries it would have sent to its end at the run's mean failed fee per try (conservative: no later fill assumed).
A window whose trigger is not on the chain recording is left as live.
Baselines: 'live' = the run as it ran; 'quiet' = QUIET replayed (arm-skip on the 4 signals + 6:2 stop) for runs without QUIET
live, the run as it ran for r27 / r28 (QUIET live). Score per window = realized + rent back - failed-try fees (MEASURED).
Unit = window; bootstrap 10,000 resamples of windows within each run, summed over runs.
usage: g1_gate.py [--clean-only] [--cut NS]   (r28 is split at the 20:58:00 PKT holdout cut: r28pre / r28clean)"""
import sys, json, argparse, collections
import numpy as np
import flatlib as FL, evalcore as EC

CUT = 1793116680 * 10**9            # 20:58:00 PKT: the holdout cut of the first report
ORDER = ["a19", "a20", "f21", "f22", "f23", "f24", "r24", "r25", "r26", "r27", "r28pre"]
FLAGS = {"a20": "both servers pre-sent 01:20-02:00 (self-competition)", "f21": "both servers pre-sent 01:20-02:00 (self-competition)"}


def night(t_ns):
    h = int(((t_ns / 1e9 + FL.PKT) % 86400) // 3600)
    return h >= 22 or h < 7


def gate_run(O, W, run, base, M):
    """per window: (base score, gate score, removed fill info)"""
    rate = sum(w["fail_fee"] for w in W) / max(sum(len(w["tries"]) for w in W), 1)
    bskip, bstops = EC.base_cfg(run, "primary" if base == "quiet" else "asrun")
    out = []
    for w in W:
        b = EC.run_rules(w, O, skip=bskip(w), stops=bstops)
        if b["skipped"] or w["k_trig"] is None:
            out.append((w, b["score"], b["score"], None)); continue
        fees = 0; fill_kept = b["fill_kept"]
        for k, t in enumerate(w["tries"]):
            if b["stop_k"] is not None and k >= b["stop_k"]: break
            ok = O.upto(w, t["pos"]) >= M
            if ok: fees += t["fee"]
            if t["fill"] and b["fill_kept"]: fill_kept = ok
        rm = None
        if w["filled"] and b["fill_kept"] and not fill_kept:
            fees += max(w["en_slot"] - w["fill"]["slot"], 0) * w["k"] * rate
            rm = dict(net=w["net"], flat=bool(w.get("flat")), t=w["t"], mint=w["mint"])
        g = ((w["net"] if (w["filled"] and fill_kept) else 0) - fees)
        out.append((w, b["score"], g, rm))
    return out


def summarize(rows):
    S = collections.Counter()
    for (w, b, g, rm) in rows:
        S["base"] += b / 1e9; S["gate"] += g / 1e9; S["windows"] += 1
        if w["filled"]: S["fills"] += 1; S["flats"] += bool(w.get("flat"))
        if rm:
            if rm["net"] > 0: S["win_rm"] += 1; S["win_sol"] += rm["net"] / 1e9
            else: S["lose_rm"] += 1; S["lose_sol"] += rm["net"] / 1e9
            if rm["flat"]: S["flat_rm"] += 1; S["flat_sol"] += rm["net"] / 1e9
    S["gain"] = S["gate"] - S["base"]
    return S


def boot(groups, n=10000, seed=11):
    rng = np.random.default_rng(seed); tot = np.zeros(n)
    for g in groups:
        g = np.asarray(g, float)
        if len(g): tot += g[rng.integers(0, len(g), size=(n, len(g)))].sum(1)
    return float(np.percentile(tot, 5)), float(np.percentile(tot, 95)), float((tot > 0).mean())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--clean-only", action="store_true"); ap.add_argument("--out", default="g1_gate")
    A = ap.parse_args()
    phases = sorted(set(p for r in FL.RUNS for p in FL.RUNS[r]["phases"])) if not A.clean_only else sorted(FL.RUNS["r28"]["phases"])
    C = FL.Chain(tuple(phases)); O = EC.Others(C)
    runs = {}
    if not A.clean_only:
        for r in ORDER[:-1]: runs[r] = FL.load_base(r)["W"]
    W28 = FL.load_base("r28")["W"]
    runs["r28pre"] = [w for w in W28 if w["t"] <= CUT]
    runs["r28clean"] = [w for w in W28 if w["t"] > CUT]
    res = {}
    for M in (1, 2):
        for base in ("live", "quiet"):
            for r, W in runs.items():
                run = "r28" if r.startswith("r28") else r
                res[(M, base, r)] = gate_run(O, W, run, base, M)
    out = {"runs": {}, "totals": {}}
    for M in (1, 2):
        print(f"\n=== GATE M = {M}  (gain in SOL; winners / losers removed with their live net; flats removed)")
        print(f"{'run':10s} {'size':>5s} {'hours (PKT)':>13s} {'win':>4s} {'fills':>5s} | {'live':>8s} {'gain':>8s} | {'QUIET base':>10s} {'gain':>8s} | {'winners rm':>15s} {'losers rm':>15s} {'flats rm':>12s} | flag")
        for r in [x for x in ORDER + ["r28clean"] if x in runs]:
            W = runs[r]
            if not W: continue
            SL = summarize(res[(M, "live", r)]); SQ = summarize(res[(M, "quiet", r)])
            size = W[0]["spend"] / 1e9
            span = f"{FL.hm(min(w['t'] for w in W), '%H:%M')}-{FL.hm(max(w['t'] for w in W), '%H:%M')}"
            print(f"{r:10s} {size:5.2f} {span:>13s} {int(SL['windows']):4d} {int(SL['fills']):5d} | {SL['base']:+8.4f} {SL['gain']:+8.4f} | {SQ['base']:+10.4f} {SQ['gain']:+8.4f} | "
                  f"{int(SQ['win_rm']):3d} ({SQ['win_sol']:+.4f}) {int(SQ['lose_rm']):3d} ({SQ['lose_sol']:+.4f}) {int(SQ['flat_rm']):3d}/{int(SQ['flats']):<3d}({SQ['flat_sol']:+.3f}) | {FLAGS.get(r, '')}")
            out["runs"][f"M{M}:{r}"] = dict(live=dict(SL), quiet=dict(SQ), size=size, span=span)
        # totals over the 11 runs (r28clean excluded: reported on its own)
        R11 = [r for r in ORDER if r in runs]
        for base in ("live", "quiet"):
            S = collections.Counter()
            for r in R11: S.update(summarize(res[(M, base, r)]))
            gains = [[(g - b) / 1e9 for (w, b, g, rm) in res[(M, base, r)]] for r in R11]
            lo, hi, pp = boot(gains)
            npos = sum(1 for r in R11 if summarize(res[(M, base, r)])["gain"] > 1e-12); nneg = sum(1 for r in R11 if summarize(res[(M, base, r)])["gain"] < -1e-12)
            print(f"TOTAL 11 runs vs {base:5s}: {S['base']:+.4f} -> {S['gate']:+.4f}  gain {S['gate'] - S['base']:+.4f} [5-95% {lo:+.4f}, {hi:+.4f}] P(>0) {pp:.2f} | runs + {npos} / - {nneg} | "
                  f"winners rm {int(S['win_rm'])} ({S['win_sol']:+.4f}) losers rm {int(S['lose_rm'])} ({S['lose_sol']:+.4f}) flats rm {int(S['flat_rm'])}/{int(S['flats'])} ({S['flat_sol']:+.4f})")
            out["totals"][f"M{M}:{base}"] = dict(S, gain=S["gate"] - S["base"], p5=lo, p95=hi, p_pos=pp, runs_pos=npos, runs_neg=nneg)
        # splits (QUIET baseline), per window
        for name, key in (("size", lambda w: "0.34-0.40" if w["spend"] < 450_000_000 else "0.50"), ("hours", lambda w: "night 22-07" if night(w["t"]) else "day 07-22")):
            grp = collections.defaultdict(lambda: collections.Counter()); gg = collections.defaultdict(lambda: collections.defaultdict(list))
            for r in R11:
                for (w, b, g, rm) in res[(M, "quiet", r)]:
                    k = key(w); G = grp[k]
                    G["gain"] += (g - b) / 1e9; G["windows"] += 1; G["fills"] += bool(w["filled"])
                    if rm:
                        if rm["net"] > 0: G["win_rm"] += 1; G["win_sol"] += rm["net"] / 1e9
                        else: G["lose_rm"] += 1; G["lose_sol"] += rm["net"] / 1e9
                    gg[k][r].append((g - b) / 1e9)
            for k, G in sorted(grp.items()):
                lo, hi, pp = boot(list(gg[k].values()))
                print(f"   split {name:5s} {k:12s}: windows {int(G['windows']):5d} fills {int(G['fills']):4d} gain {G['gain']:+.4f} [{lo:+.4f}, {hi:+.4f}] P(>0) {pp:.2f} | "
                      f"winners rm {int(G['win_rm'])} ({G['win_sol']:+.4f}) losers rm {int(G['lose_rm'])} ({G['lose_sol']:+.4f})")
                out["totals"][f"M{M}:split:{name}:{k}"] = dict(G, p5=lo, p95=hi, p_pos=pp)
    # the removed fills of the clean slice, listed
    for M in (1, 2):
        for (w, b, g, rm) in res[(M, "quiet", "r28clean")]:
            if rm: print(f"   clean slice M={M}: removed {FL.hm(rm['t'])} {rm['mint'][:8]} net {rm['net'] / 1e9:+.4f}{' (flat)' if rm['flat'] else ''}")
    json.dump(out, open(f"{FL.D}/{A.out}.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
