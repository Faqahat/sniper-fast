import json
from collections import Counter

POSC = json.load(open("/root/sel2/pos_creator.json"))
NEGC = json.load(open("/root/sel2/neg_creator.json"))
CNT = json.load(open("/root/sel2/creator_counts.json"))
POSF = json.load(open("/root/sel/pos_feat.json"))
NEGF = json.load(open("/root/sel/neg_feat.json"))
BUYSLOT = json.load(open("/root/sel/pos.json")).get("buyslot", {})


def build(creatord, featd, label, slotfb=None):
    slotfb = slotfb or {}
    rows = []
    for m, cv in creatord.items():
        if cv.get("status") != "ok":
            continue
        cr = cv.get("creator")
        cnt = CNT.get(cr)
        if cnt is None:
            continue
        slot = featd.get(m, {}).get("create_slot") or slotfb.get(m)
        if not slot:
            continue
        rows.append({"mint": m, "y": label, "slot": slot, "creator": cr, "devcount": cnt})
    return rows


pos = build(POSC, POSF, 1, BUYSLOT)
neg = build(NEGC, NEGF, 0)
pslots = sorted(r["slot"] for r in pos)
lo, hi = pslots[0], pslots[-1]
neg = [r for r in neg if lo <= r["slot"] <= hi]
P, N = len(pos), len(neg)
base = P / (P + N)
print(f"DATASET (dev-identity): pos={P} neg(in-window)={N} base={base:.4f}")
print(f"coverage: pos creators ok w/ count & slot = {P}/361 ; neg = {N} in-window\n")

# distribution of devcount
def dist(rows, lab):
    c = Counter(min(r["devcount"], 6) for r in rows)
    tot = len(rows)
    print(f"{lab} devcount distribution (6 = 6+):")
    for k in sorted(c):
        print(f"   =={k if k<6 else '6+'}: {c[k]:4d} ({c[k]/tot:.3f})")


dist(pos, "HIS BUYS")
dist(neg, "IGNORED FIELD")

# fraction one-and-done
p1 = sum(1 for r in pos if r["devcount"] == 1) / P
n1 = sum(1 for r in neg if r["devcount"] == 1) / N
print(f"\n*** one-and-done (devcount==1): HIS={p1:.3f}  IGNORED={n1:.3f}  lift={p1/n1 if n1 else float('inf'):.2f} ***")
pS = sum(1 for r in pos if r["devcount"] >= 2) / P
nS = sum(1 for r in neg if r["devcount"] >= 2) / N
print(f"    serial (devcount>=2):      HIS={pS:.3f}  IGNORED={nS:.3f}")

allrows = sorted(pos + neg, key=lambda r: r["slot"])


def eval_rule(fn, rows, name):
    Pn = sum(r["y"] for r in rows)
    sel = [r for r in rows if fn(r)]
    if not sel:
        print(f"  {name:28s} sel=0"); return
    tp = sum(r["y"] for r in sel)
    b = Pn / len(rows)
    print(f"  {name:28s} sel={len(sel):4d} tp={tp:3d} prec={tp/len(sel):.3f} recall={tp/Pn:.3f} lift={(tp/len(sel))/b:.2f}")


print("\n=== RULE devcount==1 (one-and-done) : IN-SAMPLE (full) ===")
eval_rule(lambda r: r["devcount"] == 1, allrows, "devcount==1")
print("=== RULE devcount>=2 (serial) : IN-SAMPLE (full) ===")
eval_rule(lambda r: r["devcount"] >= 2, allrows, "devcount>=2")

# TIME SPLIT
cut = int(len(allrows) * 0.6)
ss = allrows[cut]["slot"]
train = [r for r in allrows if r["slot"] < ss]
test = [r for r in allrows if r["slot"] >= ss]
print(f"\n=== TIME SPLIT @slot {ss}: train n={len(train)} pos={sum(r['y'] for r in train)} base={sum(r['y'] for r in train)/len(train):.3f} | test n={len(test)} pos={sum(r['y'] for r in test)} base={sum(r['y'] for r in test)/len(test):.3f} ===")
print(" devcount==1 TRAIN:"); eval_rule(lambda r: r["devcount"] == 1, train, "devcount==1")
print(" devcount==1 TEST :"); eval_rule(lambda r: r["devcount"] == 1, test, "devcount==1")

# also devcount<=2, <=3 variants
for thr in (2, 3):
    print(f"\n devcount<={thr} TRAIN:"); eval_rule(lambda r, t=thr: r["devcount"] <= t, train, f"devcount<={thr}")
    print(f" devcount<={thr} TEST :"); eval_rule(lambda r, t=thr: r["devcount"] <= t, test, f"devcount<={thr}")
