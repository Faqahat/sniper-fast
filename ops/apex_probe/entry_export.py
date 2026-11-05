#!/usr/bin/env python3
"""APEX-PROBE entry score: export the APEX-3 entry model (exact copy of run3_lib's walk-forward GBDT) for apex_probe.

The model, its threshold and the creator history are taken from the APEX-3 code itself (run3_lib.py / ev3.py / gbdt_np.py,
imported from --code), so the probe scores with the SAME trees, bin edges and history the backtest used:
  features (run3_lib X, history labels float32 as run3_lib computes them): dev_sol, bund_sol, bund_users, u, hour PKT, n_hist, mean label, mean fol2, frac label>0,
                         s since the creator's last resolved launch, max fol2   (history = launches resolved >= 15 s earlier)
  score = F0 + sum_t 0.05 * leaf_t(bins)   (gbdt_np.fit, 300 rounds, depth 3, seed 0; bins: 32-quantile edges of the
          training rows, side=right, +1; NaN -> bin 0)
  threshold for day d = q0.5 of the day-(d-1) model's scores on day-(d-1) watchlist picks (run4.py: entry q0.5)

Outputs (OUT dir):
  entry_model.json      LIVE: model trained on every recorded day (= the next day's walk-forward model), thr = q0.5 of
                        the last recorded day's picks scored by that day's model, the full creator history
  entry_model_val.json  VALIDATION: the last recorded day's model (trained on the earlier days) + its threshold
  entry_cases.jsonl     the last recorded day's launches: probe inputs (dev_sol, bund_sol, bund_users, u, bt, creator),
                        run3_lib's feature row X and score (repr strings: exact doubles), sel/pick, create slot/idx
  watchlist_apex3.json  the APEX-3 walk-forward watchlist for the NEXT day (ev3.watch: >=3 launches, sum>0, mean>2 mSOL,
                        CreateEvent creator) with bundle_txs_median (median bundle trades) as the probe's bundle hint
Floats are written as repr strings (shortest round-trip): the probe parses them to the identical double.

usage: entry_export.py [--code /home/moiz/sniper-apexcmp/code] [--out DIR]
"""
import sys, os, json, time, hashlib, collections
import numpy as np

a = sys.argv[1:]
def opt(k, d):
    return a[a.index(k) + 1] if k in a else d
CODE = opt("--code", "/home/moiz/sniper-apexcmp/code")
OUT = opt("--out", "/home/moiz/sniper-data/apex3/probe_entry")
sys.path.insert(0, CODE)
sys.path.insert(1, "/home/moiz/sniper-apexsnipe")
t0 = time.time()
import run3_lib as R3          # runs the APEX-3 walk-forward (L, X, Y, sel, score) exactly as REPORT.md
import gbdt_np as GB
from ev3 import watch, s2_label
L, X, Y, day, sel, score, RUNS = R3.L, R3.X, R3.Y, R3.day, R3.sel, R3.score, R3.RUNS
ND = len(RUNS)
print(f"run3_lib: {len(L)} launches, {ND} days, {time.time() - t0:.0f} s", flush=True)
R = repr

def edges_of(trm):
    """gbdt_np.binize's edges (same code) for the training mask"""
    out = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[trm & ~np.isnan(x)]
        out.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])) if len(xt) else np.array([]))
    return out

def flat(t, nodes):
    """tree -> flat node list: [f, b, left, right] or [-1, leaf]"""
    i = len(nodes); nodes.append(None)
    if "w" in t: nodes[i] = [-1, R(float(t["w"]))]; return i
    l = flat(t["l"], nodes); r = flat(t["r"], nodes); nodes[i] = [int(t["f"]), int(t["b"]), l, r]; return i

def train(d):
    """run3_lib's model for day d (trained on days < d): returns (F0, trees, edges, f)"""
    tr = day < d
    trm = tr.copy(); va = np.zeros(len(L), bool); last = np.flatnonzero(tr)[int(tr.sum() * .85):]; trm[last] = False; va[last] = True
    Bm = GB.binize(X, trm); trees, f = GB.fit(Bm, Y, trm, va, rounds=300, depth=3)
    p0 = Y[trm].mean(); F0 = np.log(p0 / (1 - p0))
    return F0, trees, edges_of(trm), f, int(trm.sum())

def model_json(d, thr, name):
    F0, trees, E, f, ntr = train(d)
    T = []
    for t in trees:
        nodes = []; flat(t, nodes); T.append(nodes)
    m = dict(name=name, version=1, model_day=d, trained_on=[RUNS[k] for k in range(min(d, ND))], n_train=ntr,
             features=["dev_sol", "bund_sol", "bund_users", "u", "hour_pkt", "n_hist", "mean_label", "mean_fol2", "frac_label_pos",
                       "since_last_s", "max_fol2"],
             f0=R(float(F0)), lr=R(0.05), edges=[[R(float(v)) for v in e] for e in E], trees=T,
             thr=R(float(thr)), thr_rule="q0.5 of the previous day's watchlist picks' scores", resolve_s=15, hour_offset_h=5,
             u_default=R(float(np.nanmedian(X[day < d, 3]))), u_note="u (create index / block size) is not visible before signing: "
             "the probe uses the PoH position when the create came with PoH, else this training median",
             data_end_bt=int(max(r[2] for r in L)))
    return m, f

def hist_json():
    H = collections.defaultdict(list)
    for r in L:
        i5 = r[5]; lab = s2_label(r)
        # run3_lib's label is a numpy float32 (float32 replay value - costs) or the python float -CREV (no fill): np.mean
        # then runs in float32 when every label of the creator's history is float32, else in float64 -> keep the type
        H[r[1]].append([int(r[2]), R(float(lab)), R(float(i5["fol2"])), int(isinstance(lab, np.float32))])
    return H

sha = {k: hashlib.sha256(open(f"{CODE}/{k}.py", "rb").read()).hexdigest() for k in ("run3_lib", "ev3", "s3_sim")}
sha["gbdt_np"] = hashlib.sha256(open("/home/moiz/sniper-apexsnipe/gbdt_np.py", "rb").read()).hexdigest()
os.makedirs(OUT, exist_ok=True)
H = hist_json()

# ---- validation model: the last recorded day's model, which must reproduce run3_lib's score on that day exactly
dv = ND - 1
thr_v = float(np.nanquantile(score[(day == dv - 1) & sel], 0.5))
mv, fv = model_json(dv, thr_v, "APEX-3 entry (validation: day %d model)" % dv)
dd = np.abs(fv[day == dv] - score[day == dv]).max()
print(f"validation model day {dv}: re-fit vs run3_lib score max abs diff {dd:.3g} (must be 0)", flush=True)
assert dd == 0, "re-fit differs from run3_lib"
mv.update(hist=H, code=CODE, code_sha=sha)
json.dump(mv, open(f"{OUT}/entry_model_val.json", "w"))

# ---- live model: trained on every recorded day; thr = q0.5 of the last day's picks scored by the last day's model
thr_l = float(np.nanquantile(score[(day == ND - 1) & sel], 0.5))
ml, fl = model_json(ND, thr_l, "APEX-3 entry (live: next-day model)")
ml.update(hist=H, code=CODE, code_sha=sha)
json.dump(ml, open(f"{OUT}/entry_model.json", "w"))

# ---- cases: the last recorded day's launches (probe inputs + run3_lib X row + score + live-model score)
n = 0
with open(f"{OUT}/entry_cases.jsonl", "w") as fo:
    for i in np.flatnonzero(day == dv):
        r = L[i]; i5 = r[5]
        fo.write(json.dumps(dict(mint=r[0], creator=r[1], bt=int(r[2]), slot=int(r[3]), idx=int(r[4]), dev_sol=R(float(i5["dev_sol"])),
                                 bund_sol=R(float(i5["bund_sol"])), bund_users=int(i5["bund_users"]), nb=int(i5["nb"]), u=R(float(i5["u"])),
                                 x=[R(float(v)) for v in X[i]], score=R(float(score[i])), score_live=R(float(fl[i])),
                                 sel=bool(sel[i]), pick=bool(sel[i] and np.isfinite(score[i]) and score[i] >= thr_v))) + "\n"); n += 1

# ---- APEX-3 watchlist for the next day (same rule as the backtest; CreateEvent creator)
W, Hl = watch(L, ND + 1, s2_label)
byc = collections.defaultdict(list)
for r in L: byc[r[1]].append(r)
wl = []
for c in sorted(W[ND]):
    rs = byc[c]; labs = Hl[c]
    wl.append(dict(creator=c, n_judged=len(labs), label_sum_sol=round(float(sum(labs)), 4), label_mean_msol=round(float(np.mean(labs)) * 1e3, 2),
                   launches_total=len(rs), last_launch_bt=int(max(r[2] for r in rs)),
                   bundle_txs_median=float(np.median([r[5]["nb"] for r in rs])), dev_sol_median=round(float(np.median([r[5]["dev_sol"] for r in rs])), 3)))
wl.sort(key=lambda d: -d["label_sum_sol"])
json.dump(dict(built_utc=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), data_end_bt=int(max(r[2] for r in L)),
               rule="APEX-3 ev3.watch: CreateEvent creator, judged on all recorded days: >=3 launches, sum(label)>0, mean>2 mSOL; label = pos-A 0.4 SOL h2 replay net - 2.7 mSOL",
               note="bundle_txs_median = median creator-bundle TRADES after the create (s3 info nb), used as the probe's bundle-wait hint",
               n_creators=len(wl), creators=wl), open(f"{OUT}/watchlist_apex3.json", "w"), indent=1)
print(f"wrote {OUT}: val model day {dv} thr {thr_v:.6f} ({len(mv['trees'])} trees), live model thr {thr_l:.6f} ({len(ml['trees'])} trees), "
      f"{n} cases ({int(sel[day == dv].sum())} picks), history {len(H)} creators, next-day watchlist {len(wl)}; {time.time() - t0:.0f} s", flush=True)
