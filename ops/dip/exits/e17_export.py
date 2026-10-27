#!/usr/bin/env python3
# e17: export the learned exit (3-seed GBDT ensemble) as one JSON bundle an engine port can read (same idea as the M2 bundle):
# feature list with definitions, per-model bin edges (exact floats as strings), trees (feature index, bin threshold, leaves),
# decision rule. Self-check: re-scoring the study rows from the JSON reproduces the study's predictions exactly.
# -> /home/moiz/sniper-data/exits/exit_learned_ens3.json
import sys, os, json, pickle, hashlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e_gbdt as GT, gbdt_np as GB, e04_learn as L4

DEF = {
    "k": "slots since our buy's slot (tick k: decision at the first feed trade of slot s_in + k)",
    "ms_in": "block-clock ms from our buy's landing to the start of slot s_in + k",
    "r": "position value now / buy SOL - 1 (curve value after the sell's pump fee, both fees included)",
    "r_peak": "max of r since our buy (incl. right after the buy)", "r_dd": "r_peak - r",
    "r_d1": "r - r at the previous tick (tick 0 = right after our buy)", "r_d2": "r - r two ticks ago", "r_d4": "r - r four ticks ago",
    "bsol1": "outside buy SOL in slot s-1 (after our buy only)", "ssol1": "outside sell SOL in slot s-1", "bsol2": "buy SOL in slots s-2..s-1",
    "ssol2": "sell SOL in slots s-2..s-1", "bsol4": "buy SOL in slots s-4..s-1", "ssol4": "sell SOL in slots s-4..s-1",
    "bsol_e": "outside buy SOL since our buy", "ssol_e": "outside sell SOL since our buy", "nb1": "outside buys in slot s-1", "ns1": "outside sells in slot s-1",
    "nb2": "outside buys in slots s-2..s-1", "nb_e": "outside buys since our buy", "ns_e": "outside sells since our buy", "nbuyer_e": "distinct buyers since our buy",
    "tgb_e": "buys by the 75 fast dip bots (modelcheck targets.txt) since our buy", "tgb2": "fast-bot buys in slots s-2..s-1",
    "tgs_e": "fast-bot sells since our buy", "cohb_e": "cohort (sel/cohort_train.json, minus the 75) buys since our buy", "cohs_e": "cohort sells since our buy",
    "bot_hold": "fast/cohort bots that bought since the dump (incl. before our buy) and have not sold", "bot_hold_sol": "their buy SOL",
    "stall_slots": "slots since the last outside buy (since our buy; k + 0.5 if none)", "stall_ms": "block-clock ms since the last outside buy (or since our buy)",
    "stall01_slots": "slots since the last outside buy >= 0.1 SOL", "maxb2": "largest outside buy in slots s-2..s-1 (SOL)", "maxs2": "largest outside sell in slots s-2..s-1",
    "bigs_e": "outside sells >= 1 SOL since our buy", "dev_s_e": "creator sell SOL since our buy", "vsol": "curve virtual SOL now (SOL)",
    "age_slots": "token age in slots at the tick", "since_dump": "slots since the dump's slot", "tg_dump": "distinct fast bots that bought since the dump",
    "coh_dump": "distinct cohort bots that bought since the dump", "tg_hold": "distinct fast bots that bought since the dump and still hold",
    "m2": "M2 score of the dump (engine bundle)", "drop": "dump price drop %", "dump_sol": "dump sell SOL", "ratio_in": "our entry price / post-dump price",
    "ahead_in": "trades between the dump and our buy", "L_in": "block-clock ms from the dump to our buy", "grp_in": "leader client group of the dump slot (0 Jito, 1 BAM, 2 Harmonic, 3 HarmonicFD, 4 FD, 5 Rakurai, 6 other)",
    "nhold_in": "fast/cohort bots holding at our buy (bought since the dump)", "grp_now": "leader client group of slot s_in + k", "age_s_in": "token age at the dump (s)",
    "curve_in": "curve SOL at the dump"}


def tree_json(t):
    if "w" in t: return {"w": repr(float(t["w"]))}
    return {"f": t["f"], "b": t["b"], "l": tree_json(t["l"]), "r": tree_json(t["r"])}


if __name__ == "__main__":
    M = pickle.load(open(f"{E.DATA}/e04b_ENS3_model.pkl", "rb"))
    d = V.Data(); X, names = L4.build_matrix(d)
    models = []; preds = []
    for p in M["ensemble"]:
        m = pickle.load(open(p, "rb")); mm = m["models"][0]
        assert m["names"] == names
        models.append(dict(edges=[[repr(float(x)) for x in e] for e in mm["edges"]], F0=repr(float(mm["model"]["F0"])), lr=repr(float(mm["model"]["lr"])),
                           trees=[tree_json(t) for t in mm["model"]["trees"]], horizons=m["H"]))
        preds.append(GT.predict(mm["model"], GT.binize(X, mm["edges"])))
    # self-check: score from the JSON structures
    def score_json(mj, X):
        E_ = [np.array([float(x) for x in e]) for e in mj["edges"]]; Bm = GT.binize(X, E_)
        out = np.full(len(X), float(mj["F0"])); lr = float(mj["lr"])
        def walk(t, rows):
            if "w" in t: out[rows] += lr * float(t["w"]); return
            go = Bm[rows, t["f"]] <= t["b"]; walk(t["l"], rows[go]); walk(t["r"], rows[~go])
        for t in mj["trees"]: walk(t, np.arange(len(X)))
        return out
    sub = np.random.default_rng(0).choice(len(X), 200000, replace=False)
    diffs = [np.abs(score_json(mj, X[sub]) - p[sub]).max() for mj, p in zip(models, preds)]
    B = dict(kind="dip_exit_learned", version=1, built="10-25 PKT", features=names, definitions={k: DEF.get(k, "") for k in names},
             binning="bin = 1 + number of edges < x (searchsorted right); NaN -> 0; go left when bin <= b",
             decision=f"at each tick k = 1..{M['cap'] - 1}: mean of the 3 model scores (F0 + lr * sum of leaves) = predicted SOL advantage of holding; "
                      f"SELL when it is <= {M['theta']} SOL; forced sell at tick {M['cap']}",
             theta=repr(float(M["theta"])), cap=M["cap"], models=models,
             lists=dict(fast_bots="ops/dip/modelcheck/targets.txt (75)", cohort="ops/overnight/sel/cohort_train.json"))
    s = json.dumps(B)
    open(f"{E.DATA}/exit_learned_ens3.json", "w").write(s)
    print(f"exported {len(names)} features, {sum(len(m['trees']) for m in models)} trees; sha256 {hashlib.sha256(s.encode()).hexdigest()[:16]}; "
          f"JSON re-score max |diff| per model {[float(x) for x in diffs]}")
