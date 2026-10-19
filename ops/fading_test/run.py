#!/usr/bin/env python3
import json, itertools, sys
sys.path.insert(0,"/root/fading_test")
from fading import simulate, stats, evalc, FEATS, TRAIN, VAL, E
SIZE=0.5
BASE=dict(E.SHIP)  # derisk .30 ride 1.40 trail .92 cut .95 ladder .25 cap 40

def mk(**kw):
    p=dict(BASE); p.update(kw); return p

def subset_stats(feats, P, lo=None, hi=None):
    """mean net R on tokens with peak in [lo,hi). returns (n, meanR, medR, winpct, totR)."""
    sel=[f for f in feats if (lo is None or f["peak"]>=lo) and (hi is None or f["peak"]<hi)]
    pnls=[simulate(f["entry"],f["entry_slot"],f["path"],P,SIZE) for f in sel]
    s=stats(pnls)
    return s

def full(feats,P):
    return stats(evalc(feats,P,SIZE))

# ---- variants ----
VARIANTS={
 "CURRENT(instant fade)":      mk(fade_mode="instant"),
 "NO-FADING":                  mk(fade_mode="off"),
 "PATIENT N=3 (deep.90)":      mk(fade_mode="patient", fade_consec_n=3, fade_deep=0.90),
 "PATIENT N=5 (deep.90)":      mk(fade_mode="patient", fade_consec_n=5, fade_deep=0.90),
 "PATIENT deep-only(.90)":     mk(fade_mode="patient", fade_consec_n=999, fade_deep=0.90),
}

def row(name,P):
    tr=full(TRAIN,P); va=full(VAL,P)
    # subsets on VAL (OOS)
    run15=subset_stats(VAL,P,lo=1.5); run20=subset_stats(VAL,P,lo=2.0)
    dud  =subset_stats(VAL,P,hi=1.1)
    return {"name":name,"P":P,"train":tr,"val":va,
            "run15":run15,"run20":run20,"dud":dud}

core=[row(n,p) for n,p in VARIANTS.items()]

# ---- combo sweep: NO-FADING x cut_r x ride_mult x cap ----
caps={"9s":40,"15s":70,"20s":93}
combos=[]
for fm in ["off"]:
    for cut in [0.95,0.90,0.85,0.80]:
        for ride in [1.2,1.3,1.4]:
            for capn,caps_v in caps.items():
                P=mk(fade_mode=fm,cut_r=cut,ride_mult=ride,cap_slots=caps_v)
                nm=f"NOFADE cut{cut} ride{ride} cap{capn}"
                combos.append(row(nm,P))
# also patient combos with lowered cut
for cut in [0.90,0.85,0.80]:
    for ride in [1.3,1.4]:
        P=mk(fade_mode="patient",fade_consec_n=3,fade_deep=0.90,cut_r=cut,ride_mult=ride,cap_slots=70)
        combos.append(row(f"PATIENT3 cut{cut} ride{ride} cap15s",P))

ALL=core+combos
# rank by TRAIN mean (model selection on train only)
ranked=sorted(ALL,key=lambda r:r["train"]["mean"],reverse=True)

def fmt(s):
    return f"{s['mean']:+.4f}/{s['median']:+.4f}/{s['win']*100:4.1f}%/{s['tot']:+7.2f}"

cur=next(r for r in core if r["name"].startswith("CURRENT"))

print("="*120)
print("CORE VARIANTS  (mean/median/win/totR).  TRAIN n=%d  VAL n=%d"%(len(TRAIN),len(VAL)))
print("%-26s | %-32s | %-32s | VAL-run>=1.5x mean(n) | VAL-dud<1.1x mean(n)"%("variant","TRAIN net","VAL net(OOS)"))
for r in core:
    print("%-26s | %-32s | %-32s | %+.4f (%d) | %+.4f (%d)"%(
        r["name"],fmt(r["train"]),fmt(r["val"]),
        r["run15"]["mean"],r["run15"]["n"],r["dud"]["mean"],r["dud"]["n"]))
print()
print("TOP 12 by TRAIN mean (OOS = VAL):")
print("%-34s | TRAIN mean | VAL mean | VAL med | VAL win | VAL tot | run>=1.5x | run>=2x | dud<1.1x"%"config")
for r in ranked[:12]:
    print("%-34s | %+.4f    | %+.4f  | %+.4f | %5.1f%% | %+6.2f | %+.4f(%d) | %+.4f(%d) | %+.4f(%d)"%(
        r["name"],r["train"]["mean"],r["val"]["mean"],r["val"]["median"],r["val"]["win"]*100,r["val"]["tot"],
        r["run15"]["mean"],r["run15"]["n"],r["run20"]["mean"],r["run20"]["n"],r["dud"]["mean"],r["dud"]["n"]))

json.dump({"core":[{k:(v if k in("name",) else (v if k=="P" else v)) for k,v in r.items()} for r in core],
           "ranked":[{"name":r["name"],"P":r["P"],"train":r["train"],"val":r["val"],
                      "run15":r["run15"],"run20":r["run20"],"dud":r["dud"]} for r in ALL]},
          open("/root/fading_test/results.json","w"),indent=1)
print("\nwrote results.json  (nALL=%d)"%len(ALL))
