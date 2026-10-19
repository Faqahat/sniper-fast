import sys, json, statistics as st
sys.path.insert(0,"/root/econ_102"); import econ102 as E
ROWS=E.load_backtest(); FEAT=E.build_feats(ROWS)
CO=[f for f in FEAT if f["cosnip"]>=1]
def trunc(feats, horizon):
    out=[]
    for f in feats:
        cs=f["entry_slot"]
        path=[(s,p) for s,p in f["path"] if s-cs<=horizon]
        out.append({**f,"path":path})
    return out
print(f"{'horizon(slots)':>14} | {'ALL net@0.5 mean/win':>22} | {'CO net@0.5 mean/win':>22} | {'ALL gross mean':>14}")
for h in [12,20,40,80,100000]:
    fa=trunc(FEAT,h); fc=trunc(CO,h)
    Sa=E.evalc(fa,E.SHIP,0.5); Sc=E.evalc(fc,E.SHIP,0.5); Ga=E.evalc_gross(fa,E.SHIP)
    hl="full" if h>1000 else str(h)
    print(f"{hl:>14} | {Sa['mean']:+.4f} / {Sa['win']*100:4.1f}%        | {Sc['mean']:+.4f} / {Sc['win']*100:4.1f}%        | {Ga['mean']:+.4f}")
