#!/usr/bin/env python3
"""scale test of buy hypotheses: flat-eligible outside trades on tokens 9pQQ traded in the run; precision (take rate), lift, recall. per era.
usage: c14_scale_buy.py RUN [RUN..]"""
import sys, numpy as np
D = "/home/moiz/sniper-data/rivals/9pQQ/casebook"
def load(run):
    z = np.load(f"{D}/scale_{run}.npz"); a = np.load(f"{D}/scale_aug_{run}.npz")
    d = {k: z[k] for k in ["s", "seg", "own", "holding", "age", "since_sell", "tb", "size", "utot", "ch10", "nf10", "n10", "nb10", "ntrips", "ps", "buy", "n75", "vsol", "tf"]}
    d.update({k: a[k] for k in a.files}); d["psets"] = z["psets"]; return d
def conds(d):
    ps = d["psets"]; retail = np.array([any(x in p for x in ("FLASHX8D", "6Vo3245e", "GMgnVFR8", "term9YPb", "JUP6Lkb")) for p in ps])[d["ps"]]
    p41 = np.array(["41Pr4XqE" in p for p in ps])[d["ps"]]
    ch = np.nan_to_num(d["ch10"]); ns10 = d["n10"] - d["nb10"]
    return {
     "size>=0.3": d["size"] >= 0.3, "size>=1": d["size"] >= 1, "bot(utot>=1k)": d["utot"] >= 1000, "retail-terminal": retail, "41Pr4": p41,
     "|ch10|>=5": np.abs(ch) >= 5, "dip+bounce(ch10<=-3&buy)": (ch <= -3) & d["buy"], "dip(ch10<=-3)": ch <= -3,
     "mom-ramp(ch10>=3&nf10>=1&ns10=0)": (ch >= 3) & (d["nf10"] >= 1) & (ns10 == 0), "wake(gap>=75&size>=0.2)": (d["gapo"] >= 75) & (d["size"] >= 0.2),
     "re-entry(ntrips>=1)": d["ntrips"] >= 1, "recent(5<=ss<=100)": (d["since_sell"] >= 5) & (d["since_sell"] <= 100),
     "quiet(|nf10|<0.5)": np.abs(d["nf10"]) < 0.5, "vsol<32": d["vsol"] < 32, "vsol>=80": d["vsol"] >= 80,
     "bot&size>=0.3": (d["utot"] >= 1000) & (d["size"] >= 0.3), "bot&size>=0.3&|ch10|>=5": (d["utot"] >= 1000) & (d["size"] >= 0.3) & (np.abs(ch) >= 5),
    }
for run in sys.argv[1:]:
    d = load(run)
    tok = np.zeros(d["seg"].max() + 1, bool); tok[d["seg"][d["own"]]] = True
    E = (~d["own"]) & (~d["holding"]) & (d["age"] >= 8) & ((d["since_sell"] < 0) | (d["since_sell"] >= 2)) & tok[d["seg"]]
    C = conds(d)
    for era in (1, 2, 3):
        Ee = E & (d["era"] == era)
        if Ee.sum() < 1000: continue
        t = d["tb"][Ee]; base = t.mean()
        print(f"== {run} era V{era}: eligible {Ee.sum()}, taken {t.sum()}, base take {100*base:.2f}%")
        for k, c in C.items():
            c = c[Ee]
            if c.sum() == 0: continue
            p = t[c].mean(); r = t[c].sum() / max(1, t.sum())
            print(f"   {k:34s} share {100*c.mean():5.1f}%  take {100*p:5.2f}%  lift {p/base:4.2f}  recall {100*r:5.1f}%")
