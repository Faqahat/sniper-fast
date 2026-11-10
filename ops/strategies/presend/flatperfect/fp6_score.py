#!/usr/bin/env python3
"""FLATPERFECT step 6: score the FROZEN 'FP-NOBOT' filter on run 55 ONCE (refuses to run if any frozen code file changed).
usage: fp6_score.py R55.jsonl TAG   -> /home/it/sniper-data/flatperfect/r55_score_TAG.{json,txt}
Money = presend_live_realized (MEASURED). f20 = ESTIMATE (followers 20% weaker: a blocked trade's gain above ~17 mSOL cost shrinks 20%).
Saved = -sum(realized P&L of blocked positions); w/o top5 = saved without its 5 biggest saves."""
import sys, os, json, hashlib, pickle, subprocess, collections
import numpy as np, lightgbm as lgb
HERE = "/home/it/sniper/ops/strategies/presend/flatperfect"
OUTD = "/home/it/sniper-data/flatperfect"
PY = f"{OUTD}/venv/bin/python"
sys.path.insert(0, HERE)
FR = json.load(open(f"{HERE}/FROZEN_FLAT.json"))
for c, h in FR["code_sha256"].items():
    if hashlib.sha256(open(f"{HERE}/{c}", "rb").read()).hexdigest() != h: sys.exit(f"FROZEN code changed: {c}")
for k, v in FR["kinds"].items():
    for fn, h in v["models"].items():
        if hashlib.sha256(open(f"{OUTD}/{fn}", "rb").read()).hexdigest() != h: sys.exit(f"FROZEN model changed: {fn}")
import fp2_own
from fp5_freeze import q3a, f20
path, tag = sys.argv[1], sys.argv[2]
subprocess.run([PY, f"{HERE}/fp_f2_runs.py", "r55", path], check=True)
ex = pickle.load(open(f"{OUTD}/runs/ex_r55.pkl", "rb"))
own = fp2_own.run_feats(ex)
pos = sorted(ex["pos"], key=lambda p: p["t0"])
for p in pos:
    p["key"] = f'{p["run"]}|{p["mint"]}|{p["pid"]}|{p["kind"]}|{p["w"]}'; p["cls"] = fp2_own.cls(p["pnl"])
inp = [{k: p.get(k) for k in ("key", "mint", "kind", "trig_slot", "trig_idx", "buy_slot", "buy_idx", "whale")} for p in pos]
pickle.dump(inp, open(f"{OUTD}/r55_inputs_{tag}.pkl", "wb"))
env = dict(os.environ, NP="10", CHAIN_DIR=f"{OUTD}/chain")
subprocess.run([PY, f"{HERE}/fp1_chain.py", f"{OUTD}/r55_inputs_{tag}.pkl", f"{OUTD}/r55_chain_{tag}.pkl"], check=True, env=env,
               stdout=subprocess.DEVNULL)
ch = pickle.load(open(f"{OUTD}/r55_chain_{tag}.pkl", "rb"))
spans = json.load(open(f"{OUTD}/chain/spans.json"))
smax = max(s[2] for s in spans)
FEATS = FR["features"]
rows = []
for p in pos:
    f = dict(own[p["key"]]); c = ch.get(p["key"])
    cov = c is not None and p.get("buy_slot") is not None and p["buy_slot"] + 2 <= smax
    if c: f.update(c)
    rows.append((p, cov, [f.get(k, np.nan) for k in FEATS]))
X = np.array([r[2] for r in rows], float)
score = np.full(len(rows), np.nan)
for kind, v in FR["kinds"].items():
    idx = [i for i, r in enumerate(rows) if r[0]["kind"] == kind]
    if not idx: continue
    s = np.mean([lgb.Booster(model_file=f"{OUTD}/{fn}").predict(X[idx]) for fn in sorted(v["models"])], 0)
    score[idx] = s
res = []
for i, (p, cov, _) in enumerate(rows):
    elig = not q3a(p)
    blk = bool(elig and cov and score[i] >= FR["kinds"][p["kind"]]["thr"])
    res.append({"key": p["key"], "kind": p["kind"], "t0": p["t0"], "pnl": p["pnl"], "cls": p["cls"], "cov": bool(cov), "elig": elig,
                "score": None if np.isnan(score[i]) else float(score[i]), "blocked": blk})
t0s = [r["t0"] for r in res]; hours = (max(t0s) - min(t0s)) / 3.6e12


def summ(L):
    b = [r for r in L if r["blocked"]]
    sv = sorted([-r["pnl"] for r in b], reverse=True)
    g = lambda c: (sum(r["cls"] == c for r in b), round(sum(r["pnl"] for r in b if r["cls"] == c), 3))
    return {"n": len(L), "net_all": round(sum(r["pnl"] for r in L), 3), "flats_all": sum(r["cls"] == "flat" for r in L),
            "flat_sol_all": round(sum(r["pnl"] for r in L if r["cls"] == "flat"), 3), "uncovered": sum(not r["cov"] for r in L),
            "blocked": len(b), "flats": g("flat"), "smalls": g("small"), "wins": g("win"), "biglosses": g("bigloss"),
            "saved": round(sum(sv), 3), "per_day": round(sum(sv) / hours * 24, 3) if hours else None, "wo5": round(sum(sv[5:]), 3),
            "wo5_day": round(sum(sv[5:]) / hours * 24, 3) if hours else None, "f20": round(-sum(f20(r["pnl"]) for r in b), 3)}


from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
out = {"tag": tag, "file": path, "hours": round(hours, 2), "first": datetime.fromtimestamp(min(t0s) / 1e9, PKT).isoformat(),
       "last": datetime.fromtimestamp(max(t0s) / 1e9, PKT).isoformat(), "chain_max_slot": smax,
       "all": summ(res), "T2": summ([r for r in res if r["kind"] == "T2"]), "rearm": summ([r for r in res if r["kind"] == "rearm"]),
       "rows": res}
json.dump(out, open(f"{OUTD}/r55_score_{tag}.json", "w"), indent=0)
lines = [f"R55 PROOF [{tag}] {out['first']} -> {out['last']} ({hours:.1f} h), MEASURED realized; f20 = EST"]
for k in ("all", "T2", "rearm"):
    s = out[k]
    lines.append(f"{k:5s} positions {s['n']} (net {s['net_all']:+.3f}, flats {s['flats_all']} {s['flat_sol_all']:+.3f}, uncovered {s['uncovered']}) | "
                 f"blocked {s['blocked']}: flats {s['flats'][0]} ({s['flats'][1]:+.3f}) smalls {s['smalls'][0]} ({s['smalls'][1]:+.3f}) "
                 f"wins {s['wins'][0]} ({s['wins'][1]:+.3f}) bigloss {s['biglosses'][0]} ({s['biglosses'][1]:+.3f}) | saved {s['saved']:+.3f} "
                 f"({s['per_day']:+.2f}/day) w/o top5 {s['wo5']:+.3f} ({s['wo5_day']:+.2f}/day) f20(EST) {s['f20']:+.3f}")
open(f"{OUTD}/r55_score_{tag}.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
