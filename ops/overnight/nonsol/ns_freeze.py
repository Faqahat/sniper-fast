#!/usr/bin/env python3
# Task 4: freeze the only recipe that was positive OUT-OF-SAMPLE in both directions under the strict variant
# (logistic demand model, top 2% of scores, exit t5) for a later forward test. The frozen instance is re-fit on R1+R2
# with the identical recipe (features, preprocessing, L2, iterations); threshold = 98th percentile of R1+R2 scores.
# -> /home/moiz/sniper/ops/overnight/dryrun/frozen_nonsol.json (+ .sha256)
import sys, os, json, hashlib, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol")
import ns_select as S          # rebuilds features (prints its report again; fine)
from ns_lib import *
rows = S.rows
X = S.mat(rows); y = np.array([1.0 if S.demand(r) >= 3 else 0.0 for r in rows])
m = S.fit(X, y); sc = S.score(m, X); thr = float(np.quantile(sc, 0.98))
sel = [r for r, s in zip(rows, sc) if s >= thr]
ins = {run: {Lm: summ([r for r in sel if r["run"] == run], Lm, "strict", "5.0") for Lm in (30, 45, 75)} for run in ("R1", "R2")}
oos = {}
for k in ("logit_R1_top0.02", "logit_R2_top0.02"):
    rr = {r["m"]: r for r in rows}; sl = [rr[x] for x in S.RES[k]["test"]]
    oos[k] = {f"L{Lm}_{var}_{ex}": summ(sl, Lm, var, ex) for Lm in (30, 45, 75) for var in ("base", "strict") for ex in ("3.0", "5.0", "8.0")}
F = dict(
    name="NONSOL-1 (non-SOL-quoted pump curves: demand model top 2% + first-after-bundle + sell at 5 s)",
    frozen_at_utc=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), status="WEAK CANDIDATE for a forward (paper) test only - statistically fragile (see caveats); NOT validated for live",
    universe=dict(quote="any non-SOL quote mint (CreateEvent quote_mint at +74 after the 4 pubkeys != all-zero)", mayhem=False,
                  dev_buy_in_create_tx=True, quote_must_have_a_SOL_rate=True),
    entry=dict(size_sol_eq=0.5, when="right after the dev's glued bundle closes (consecutive buy txs right after the create in the create slot)",
               guard="buy only if the curve price at our landing <= 1.005 x the post-bundle price (= we are first outside buyer)",
               landing_ms_primary=45, landing_ms_tested=[30, 45, 75], swap="SOL->quote in the same tx (or quote inventory)"),
    exit=dict(primary="sell everything 5.0 s after our buy slot (slots of 212 ms), quote -> SOL", secondary_readouts=["t3", "t8"]),
    costs_assumed=dict(buy_overhead_pct_of_size=2.0, pump_fees="this curve's protocol + creator bps (from its trade events) both sides", fill_penalty_pct=1.5,
                       swap_leg_pct_each_side=0.3, sell_tx_fee_sol=0.0005, failed_guarded_buy_sol=-0.005),
    model=dict(type="L2 logistic regression (numpy, standardized, lam=1, 600 steps, lr 1.0 effective)", label="generic (non-insider, non-fast-sniper, non-pro) buy >= 3 SOL-eq in 2-10 s after create",
               features=S.FN, mu=[float(x) for x in m["mu"]], sd=[float(x) for x in m["sd"]], w=[float(x) for x in m["w"]], b=float(m["b"]), threshold=thr,
               feature_notes=dict(q_onehot="quote class one-hot (q_pump q_usdc q_x q_pt q_oth): PUMP / USDC / xStock (mint starts Xs) / pump-token (mint ends pump) / other",
                                  ldev="log1p(dev buy SOL-eq incl. fees)", dev_share="dev tokens / 1e15", glued="glued bundle txs (cap 5)", gw="glued wallets (cap 5)", lglued="log1p(glued buy SOL-eq)",
                                  cb="creator fee bps / 100", shallow="initial virtual quote reserves < 25 SOL-eq", pic="create payer == creator", tips="create tx paid a tip",
                                  lfee="log10(max(create tx fee lamports, 5000))", cv2="CreateV2", cr_ns_="creator's earlier NON-SOL launches (>= 60 s old): log1p(count), log1p(mean generic 2-10 s demand), share with demand >= 3, none-yet flag",
                                  q_hist="(q_n60 q_dem60 q_hit60) same quote token's launches in the last 60 min (>= 60 s old): log1p(count), log1p(mean demand), share >= 3",
                                  t_="the live engine's decision-time features (shadow decide record / paper table_dump names; log1p on counts as coded); NaN -> mu"),
               note="feature code: ns_select.py feats(); rate = SOL per quote unit (hourly mid of in-tx SOL<->quote conversions, ns_rates.py)"),
    evidence=dict(out_of_sample=oos, in_sample_refit_strict_t5=ins,
                  caveats=["profit depends on the best 5 trades in every t5 cell (total without top 5 < 0); medians are negative",
                           "chosen after looking at 4 cutoffs x 5 exits x 3 landings: multiple-comparison risk; top 5% / 10% / 20% cutoffs lose",
                           "R1 placement is a block-position proxy; R2 uses our engine's arrival timelines",
                           "swap cost per leg assumed 0.3%; the measured retail all-in SOL<->quote cost is 1.2-2% per leg (includes bot fees + rent noise); at 1.5%/leg the t5 totals stay positive but smaller",
                           "small samples: 22-82 fills per test period",
                           "bootstrap 90% CI of the test totals (strict t5) includes 0 in 5 of 6 cells; P(total<=0) 0.04-0.33 (robust.txt / RESULTS.md)",
                           "R1->R2 profit comes from name waves (8 'Warhound' + 3 'Michiko Malandro' launches); one pick per name: L45 -0.69 SOL",
                           "model-variant check (variants.txt): 3 of 4 other variants lose in one direction at the top 2% -> the edge is not stable",
                           "expect ~break-even forward; do NOT trade live on this; forward test only"]),
    files=dict(table="ops/overnight/nonsol/data/table.jsonl", scripts=["ns_extract.py", "ns.py", "ns_rates.py", "ns_table.py", "ns_lib.py", "ns_select.py", "ns_robust.py", "ns_freeze.py"]))
p = "/home/moiz/sniper/ops/overnight/dryrun/frozen_nonsol.json"
s = json.dumps(F, indent=1, sort_keys=True)
open(p, "w").write(s + "\n")
h = hashlib.sha256(open(p, "rb").read()).hexdigest()
open(p + ".sha256", "w").write(f"{h}  frozen_nonsol.json\n")
print("FROZEN", p, h, "threshold", thr, "in-sample picks", len(sel), {k: {L: (v["tot"], v["fills"]) for L, v in d.items()} for k, d in ins.items()})
