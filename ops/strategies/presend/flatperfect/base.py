"""FLATPERFECT common loader. DEV runs only (r37..r54). r55 is NEVER loaded here (proof protocol)."""
import pickle, collections, sys
from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
FS = "/home/moiz/sniper-data/flatsig/runs"
OUT = "/home/moiz/sniper-data/flatperfect"
DEVRUNS = ["r37","r38","r39","r40","r41","r42","r43","r44","r45","r46","r47","r48","r49","r50","r51","r52","r53","r54"]
def cls(p):
    if p < -0.025: return "bigloss"
    if p <= 0: return "flat"
    if p < 0.025: return "small"
    return "win"
def pkt(t): return datetime.fromtimestamp(t/1e9, PKT).strftime("%m-%d %H:%M")
def load(run):
    assert run != "r55", "r55 locked until freeze"
    return pickle.load(open(f"{FS}/ex_{run}.pkl","rb"))
def positions(runs=DEVRUNS):
    P=[]
    for r in runs:
        x=load(r)
        for p in x["pos"]:
            p=dict(p); p["cls"]=cls(p["pnl"]); P.append(p)
    P.sort(key=lambda p:(p["buy_t"]))
    return P
