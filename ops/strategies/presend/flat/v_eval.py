#!/usr/bin/env python3
"""FLAT study: the FROZEN variants (FROZEN.json) on any runs, per window, with bootstrap ranges (read-only, offline).
  A   : the frozen hold rule on the engine-flat positions of the baseline (side cost included, a_eval.py)
  B   : the frozen skip / stop rule; B1_info, B2single_info: the best try-time stop and best single-feature skip (information)
  A+B : B first, then A on the positions B keeps (side cost against B's kept tries)
Unit = one live window (gain = variant score - baseline score; 0 for untouched windows). Bootstrap: 10,000 resamples of the
windows of each run (stratified by run), 5-95%. Writes /home/moiz/sniper-data/presend_flat/v_<tag>.json
usage: v_eval.py --runs r27 --tag val [--mode primary|asrun]"""
import sys, json, argparse, collections
import numpy as np
import flatlib as FL, evalcore as EC, a_core as AC, a_eval as AE

HERE = "/home/moiz/sniper/ops/strategies/presend/flat"


def skip_fn(spec):
    if not spec: return None
    def fn(w):
        if w["f"] is None: return False
        for (f, d, t) in spec:
            c = w["f"][f] <= t if d == "le" else w["f"][f] >= t
            if not c: return False
        return True
    return fn


def per_window(C, O, run, mode, F, d_react):
    B = FL.load_base(run); W = B["W"]
    out = {}
    bskip, bstops = EC.base_cfg(run, mode)
    # B variants: per-window gains
    for tag, spec, stops in (("B", F["B"].get("spec"), F["B"].get("stops") or []), ("B1_info", None, F["B1_info"]["stops"]),
                             ("B2single_info", F["B2single_info"]["spec"], [])):
        rows, S = EC.evaluate(W, O, run, mode=mode, extra_skip=skip_fn(spec), extra_stops=stops)
        g = {(w["seg"], w["w"]): (v["score"] - b["score"]) for (w, b, v) in rows}
        out[tag] = dict(S=S, g=g, rm=[dict(t=w["t"], mint=w["mint"], net=w["net"], flat=w.get("flat")) for (w, b, v) in rows if b["fill_kept"] and not v["fill_kept"]])
    # A and A+B
    for tag, spec, stops in (("A", None, []), ("A+B", F["B"].get("spec"), F["B"].get("stops") or [])):
        xs = skip_fn(spec)
        sk = (lambda w, xs=xs: bskip(w) or bool(xs and xs(w)))
        res = eval_A(C, O, run, W, B["fires"], sk, list(bstops) + list(stops), F["A"]["rule"], d_react)
        g = collections.defaultdict(float)
        for x in res: g[x["key"]] += x["gain"]
        if tag == "A+B":
            for k, v in out["B"]["g"].items(): g[k] += v
        out[tag] = dict(g=dict(g), rows=res)
    out["keys"] = [(w["seg"], w["w"]) for w in W]
    return out


def eval_A(C, O, run, W, fires, skipf, stops, rule, d_react):
    base = {}; kept_windows = {}; kept_tries = []
    for w in W:
        b = EC.run_rules(w, O, skip=skipf(w), stops=stops)
        key = (w["seg"], w["w"]); base[key] = b
        if b["skipped"]: continue
        kept_windows[key] = w
        for k, t in enumerate(w["tries"]):
            if b["stop_k"] is None or k < b["stop_k"]: kept_tries.append((key, k, t["t"]))
    rule = dict(rule); rule.setdefault("K", None); rule.setdefault("X", None)
    out = []; dropped_all = set(); blocked_all = set()
    for w in W:
        key = (w["seg"], w["w"])
        if not w["filled"] or not base[key]["fill_kept"] or not w.get("eng_flat"): continue
        P = AC.prep(C, w)
        if P is None: continue
        r = AC.walk(P, rule, d_react)
        live = P["pnl"] + P["rb"]
        dt, bw, fz = AE.side_effects(P, r, kept_tries, kept_windows, fires, run)
        side = 0; lost = 0
        for (kk, k) in dt:
            if (kk, k) in dropped_all: continue
            dropped_all.add((kk, k)); ww = kept_windows[kk]; t = ww["tries"][k]
            if t["fill"]: side -= ww["net"]; lost += 1
            else: side += t["fee"]
        for kk in bw:
            if kk in blocked_all: continue
            blocked_all.add(kk); side -= base[kk]["score"]
        out.append(dict(key=key, mint=w["mint"], t=w["t"], flat=w.get("flat"), live=live, cf=r["score"], why=r["why"], gain=(r["score"] - live) + side, side=side,
                        lost_fills=lost, blocked=len(bw), fires=len(fz)))
    return out


def boot(gs_by_run, n=10000, seed=7):
    rng = np.random.default_rng(seed)
    tot = np.zeros(n)
    for g in gs_by_run:
        g = np.asarray(g, float)
        if len(g) == 0: continue
        idx = rng.integers(0, len(g), size=(n, len(g)))
        tot += g[idx].sum(1)
    return float(np.percentile(tot, 5)), float(np.percentile(tot, 95)), float((tot > 0).mean())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", nargs="+", required=True); ap.add_argument("--tag", required=True); ap.add_argument("--mode", default="primary")
    A = ap.parse_args()
    F = json.load(open(f"{HERE}/FROZEN.json"))
    d_react = json.load(open(f"{FL.D}/a_delays.json"))["d_react_median"]
    phases = sorted(set(p for r in A.runs for p in FL.RUN_PHASES[r]))
    C = FL.Chain(phases); O = EC.Others(C)
    R = {r: per_window(C, O, r, A.mode, F, d_react) for r in A.runs}
    summary = {}
    for tag in ("A", "B", "A+B", "B1_info", "B2single_info"):
        per = {}
        for r in A.runs:
            g = R[r][tag]["g"]
            per[r] = sum(g.values()) / 1e9
        gs = [[R[r][tag]["g"].get(k, 0) / 1e9 for k in R[r]["keys"]] for r in A.runs]
        lo, hi, pp = boot(gs)
        summary[tag] = dict(per=per, total=sum(per.values()), p5=lo, p95=hi, p_pos=pp)
        extra = ""
        if tag in ("B", "B1_info", "B2single_info"):
            S = collections.Counter()
            for r in A.runs:
                for k, v in R[r][tag]["S"].items():
                    if isinstance(v, (int, float)): S[k] += v
            summary[tag]["S"] = dict(S)
            extra = (f" | winners removed {int(S['win_rm'])} ({S['win_rm_sol']:+.4f}) losers removed {int(S['lose_rm'])} ({S['lose_rm_sol']:+.4f}) flats removed "
                     f"{int(S['flat_rm'])} ({S['flat_rm_sol']:+.4f}) fees saved {S['fees_saved']:.4f} windows skipped {int(S['skipped'])}")
        else:
            rows = [x for r in A.runs for x in R[r][tag]["rows"]]
            ch = [x for x in rows if abs(x["gain"]) > 0]
            summary[tag]["n_affected"] = len(rows); summary[tag]["n_changed"] = len(ch)
            summary[tag]["better"] = sum(1 for x in rows if x["gain"] > 0); summary[tag]["worse"] = sum(1 for x in rows if x["gain"] < 0)
            summary[tag]["side"] = sum(x["side"] for x in rows) / 1e9
            extra = (f" | positions held {len(rows)} (flat on chain {sum(1 for x in rows if x['flat'])}), better {summary[tag]['better']}, worse {summary[tag]['worse']}, "
                     f"side {summary[tag]['side']:+.4f}, lost fills {sum(x['lost_fills'] for x in rows)}, blocked {sum(x['blocked'] for x in rows)}, fires {sum(x['fires'] for x in rows)}")
        name = F[tag]["name"] if tag in F else (F["A"]["name"] + " + " + F["B"]["name"] if tag == "A+B" else tag)
        print(f"[{tag}] {name}\n    " + "  ".join(f"{r} {v:+.4f}" for r, v in per.items()) + f"  | total {sum(per.values()):+.4f} (5-95% {lo:+.4f}..{hi:+.4f}, P(>0) {pp:.2f})" + extra)
    json.dump(dict(runs=A.runs, mode=A.mode, summary=summary, rows={r: {t: R[r][t].get("rows") or R[r][t].get("rm") for t in ("A", "A+B", "B", "B1_info", "B2single_info")} for r in A.runs}),
              open(f"{FL.D}/v_{A.tag}_{A.mode}.json", "w"), default=str)


if __name__ == "__main__":
    main()
