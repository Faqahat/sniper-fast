#!/usr/bin/env python3
"""WHO step 6: score every rule (rules.pkl) -- PICK / TEST r37 / r38 / PAPER, per run, CI, w/o top-1/top-5, winners vs losers skipped;
pick one finalist per family on PICK only (best PICK saving among rules with PICK w/o-top-1 > 0), then apply the pass bar.
Out: score.json, score.txt (stdout)"""
import pickle, json, collections, sys
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/who")
from w5_rules import PICK_RUNS, TEST_RUNS, R38, PAPER_RUNS

D = "/home/it/sniper-data/prevent/who"
ALL_LIVE = ["FRA21", "FRA22", "FRA23", "FRA24", "FRA26", "FRA27", "FRA28", "AMS16", "AMS17", "AMS19", "AMS20", "AMS24", "AMS25", "AMS26", "AMS27", "AMS34", "AMS35", "AMS36", "AMS37", "AMS38"]
SIX = [("AMS38", "9wU2PpxtTbEMb3XjuhhHUTF7Sv6rBYiUDCiwzVfrpump", "rearm"), ("AMS38", "HDnCHWDiQZgT5GX3bSZ1Dxg6fRZt4noU2t9SK6BwURGu", "t2"),
       ("AMS38", "7fNXHMXVed5Av9AbHQ6QfGLs59CCtFxS2C5L6RMovAQ4", "t2"), ("AMS38", "7fNXHMXVed5Av9AbHQ6QfGLs59CCtFxS2C5L6RMovAQ4", "rearm"),
       ("AMS38", "27Jgn5V6uXQddw5b6qA6YrZ9Sj8mfhSuBpKxRBMKpump", "t2"), ("AMS38", "9hGUm3RKhePWXHGP3UyJ1nvMtr4SuN41oiRff7pwaJ4k", "rearm"),
       ("AMS38", "AJvBnYDtMtY69TQyDnLW98nT6vb3ngaqqNRjRfdTpump", "rearm")]
FIVEC = ("AMS38", "5cMetpCp")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "rules"
    X = pickle.load(open(f"{D}/{src}.pkl", "rb")); meta, res = X["meta"], X["res"]
    run = np.array([m["run"] for m in meta]); mode = np.array([m["mode"] for m in meta])
    val = np.array([m["val_s"] for m in meta]); valr = np.array([m["val_r"] for m in meta]); pnl = np.array([m["pnl_s"] for m in meta])
    filled = np.array([m["filled"] for m in meta]); hours = np.array([int(m["t"] // 3600) for m in meta])
    live = mode == "live"
    pick = live & np.isin(run, PICK_RUNS); test = live & np.isin(run, TEST_RUNS); r38 = live & np.isin(run, R38); paper = mode == "paper"
    pt = pick | test
    hu, hinv = np.unique(hours[pt], return_inverse=True)
    rng = np.random.default_rng(7)
    BI = rng.integers(0, len(hu), size=(2000, len(hu)))
    six_idx = []
    for rn, mk, kd in SIX:
        k = [i for i, m in enumerate(meta) if m["run"] == rn and m["mint"] == mk and m["kind"] == kd and m["filled"]]
        six_idx.append(k[0] if k else None)
    k5 = [i for i, m in enumerate(meta) if m["run"] == "AMS38" and m["mint"].startswith("5cMetpCp") and m["filled"]]
    out = {}
    for name, (fam, sk) in res.items():
        sav = np.where(sk, -val, 0.0); savr = np.where(sk, -valr, 0.0)
        o = {"fam": fam}
        o["pick"] = float(sav[pick].sum()); o["test"] = float(sav[test].sum()); o["r38"] = float(sav[r38].sum()); o["paper"] = float(sav[paper].sum())
        o["pick_raw"] = float(savr[pick].sum()); o["test_raw"] = float(savr[test].sum()); o["r38_raw"] = float(savr[r38].sum())
        o["per_run"] = {r: float(sav[live & (run == r)].sum()) for r in ALL_LIVE}
        o["per_paper"] = {r: float(sav[paper & (run == r)].sum()) for r in PAPER_RUNS}
        pr = [o["per_run"][r] for r in PICK_RUNS]
        o["help"] = sum(1 for x in pr if x > 1e-9); o["hurt"] = sum(1 for x in pr if x < -1e-9)
        o["skip_win_share"] = float(sk[live].mean()); o["skip_fill_share"] = float(sk[live & filled].sum() / max((live & filled).sum(), 1))
        o["skip_fills_pt"] = int((sk & pt & filled).sum())
        # bootstrap over hours (PICK+TEST)
        hs = np.bincount(hinv, weights=sav[pt], minlength=len(hu))
        bs = hs[BI].sum(1); o["ci90"] = [float(np.percentile(bs, 5)), float(np.percentile(bs, 95))]
        s_pt = np.sort(sav[pt & sk])[::-1]
        tot = float(sav[pt].sum()); o["pt"] = tot
        o["wo_top1"] = tot - float(s_pt[:1].sum()); o["wo_top5"] = tot - float(s_pt[:5].sum())
        o["pick_wo_top1"] = o["pick"] - float(np.sort(sav[pick & sk])[::-1][:1].sum())
        win = pt & sk & filled & (pnl > 0); los = pt & sk & filled & (pnl < 0)
        o["skip_win_sol"] = float(pnl[win].sum()); o["skip_loss_sol"] = float(-pnl[los].sum())
        o["six"] = [None if i is None else bool(sk[i]) for i in six_idx]
        o["five_c"] = [bool(sk[i]) for i in k5]
        out[name] = o
    # finalists per family on PICK only
    fin = {}
    for fam in sorted({o["fam"] for o in out.values()}):
        c = [(o["pick"], n) for n, o in out.items() if o["fam"] == fam and o["pick_wo_top1"] > 0]
        if c: fin[fam] = max(c)[1]
    for n, o in out.items():
        p1 = o["test"] > 0; p2 = o["help"] > o["hurt"]; p3 = o["ci90"][0] > 0; p4 = o["wo_top1"] > 0; p5 = o["skip_win_sol"] <= o["skip_loss_sol"]
        o["checks"] = [p1, p2, p3, p4, p5]
        o["verdict"] = "PASS" if all(o["checks"]) else ("LEAD" if (p1 and p4) else "FAIL")
    json.dump({"rules": out, "finalists": fin}, open(f"{D}/score{'' if src == 'rules' else '_' + src}.json", "w"), indent=1)
    # print
    def line(n, o):
        return (f"{n:42s} pick {o['pick']:+6.2f} (w/o1 {o['pick_wo_top1']:+6.2f}) test {o['test']:+6.2f} r38 {o['r38']:+6.2f} | h/h {o['help']:2d}/{o['hurt']:2d} | CI [{o['ci90'][0]:+5.2f},{o['ci90'][1]:+5.2f}] "
                f"w/o1 {o['wo_top1']:+5.2f} w/o5 {o['wo_top5']:+5.2f} | skipW {o['skip_win_sol']:5.2f} skipL {o['skip_loss_sol']:5.2f} | fills {o['skip_fill_share'] * 100:4.1f}% | paper {o['paper']:+6.2f} | {o['verdict']}")
    print("ALL RULES (sorted by PICK saving @0.696 SOL)")
    for n, o in sorted(out.items(), key=lambda z: -z[1]["pick"]): print(line(n, o))
    print("\nFINALISTS (chosen on PICK only)")
    for fam, n in fin.items(): print(fam, line(n, out[n]))
    print("\nrules passing all 5 checks:", [n for n, o in out.items() if o["verdict"] == "PASS"])
    print("rules LEAD:", len([n for n, o in out.items() if o["verdict"] == "LEAD"]))


if __name__ == "__main__":
    main()
