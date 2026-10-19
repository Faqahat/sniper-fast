import json, math
from collections import Counter
from urllib.parse import urlparse

POSM = json.load(open("/root/sel2/pos_meta.json"))
NEGM = json.load(open("/root/sel2/neg_meta.json"))
POSF = json.load(open("/root/sel/pos_feat.json"))
NEGF = json.load(open("/root/sel/neg_feat.json"))
# optional recovered slots for positives whose feat slot is missing
try:
    REC = json.load(open("/root/sel2/pos_recovered_sigs.json"))
except Exception:
    REC = {}


def host(uri):
    try:
        h = urlparse(uri).netloc.lower()
        return h or "?"
    except Exception:
        return "?"


def build(metad, featd, label):
    rows = []
    for m, mv in metad.items():
        if mv.get("status") != "ok":
            continue
        fv = featd.get(m, {})
        slot = fv.get("create_slot")
        bt = fv.get("block_time")
        if not slot:
            continue
        r = {"mint": m, "y": label, "create_slot": slot, "bt": bt,
             "uri_host": host(mv.get("uri", "")),
             "has_desc": 1 if mv.get("has_desc") else 0,
             "desc_len": mv.get("desc_len", 0),
             "has_twitter": 1 if mv.get("has_twitter") else 0,
             "has_website": 1 if mv.get("has_website") else 0,
             "n_socials": mv.get("n_socials", 0),
             "name_len": mv.get("name_len", 0),
             "symbol_len": mv.get("symbol_len", 0),
             "dev_buy_sol": fv.get("dev_buy_sol"),
             "total_bundled_sol": fv.get("total_bundled_sol"),
             "n_cobundlers": fv.get("n_cobundlers")}
        rows.append(r)
    return rows


pos = build(POSM, POSF, 1)
neg = build(NEGM, NEGF, 0)
pslots = sorted(r["create_slot"] for r in pos)
lo, hi = pslots[0], pslots[-1]
neg = [r for r in neg if lo <= r["create_slot"] <= hi]
allrows = pos + neg
print(f"pos={len(pos)} neg(in-window)={len(neg)} base={len(pos)/len(allrows):.4f}  window={lo}..{hi}")

# ---- TIME SPLIT by slot median of the full labeled set ----
allrows.sort(key=lambda r: r["create_slot"])
cut = int(len(allrows) * 0.6)
splitslot = allrows[cut]["create_slot"]
train = [r for r in allrows if r["create_slot"] < splitslot]
test = [r for r in allrows if r["create_slot"] >= splitslot]
trp = sum(r["y"] for r in train); tep = sum(r["y"] for r in test)
print(f"TIME SPLIT @slot {splitslot}: train n={len(train)} pos={trp} | test n={len(test)} pos={tep}")
print(f"train base={trp/len(train):.4f} test base={tep/len(test):.4f}\n")


def host_table(rows, title):
    p = [r for r in rows if r["y"] == 1]; n = [r for r in rows if r["y"] == 0]
    ph = Counter(r["uri_host"] for r in p); nh = Counter(r["uri_host"] for r in n)
    print(f"--- {title}: host | hisN his% | negN neg% | lift ---")
    stats = {}
    for h in sorted(set(ph) | set(nh), key=lambda x: -(ph[x] + nh[x])):
        pp = ph[h] / len(p) if p else 0; npp = nh[h] / len(n) if n else 0
        lift = (pp / npp) if npp > 0 else (float('inf') if pp > 0 else 0)
        stats[h] = lift
        if ph[h] + nh[h] >= 3:
            ls = f"{lift:.2f}" if lift != float('inf') else "inf"
            print(f"  {h[:30]:30s} {ph[h]:4d} {pp:5.2f} | {nh[h]:4d} {npp:5.2f} | {ls}")
    return stats, ph, nh, len(p), len(n)


tr_stats, trph, trnh, trP, trN = host_table(train, "TRAIN host dist")
print()
host_table(test, "TEST host dist")

# ---- learn preferred-host set on TRAIN (hosts with his-lift>=1.3 and >=4 of his picks) ----
pref = set()
base_tr = trP / (trP + trN)
for h, lift in tr_stats.items():
    if trph[h] >= 4 and lift >= 1.3:
        pref.add(h)
print(f"\nPREFERRED HOSTS (learned on TRAIN, lift>=1.3 & his>=4): {sorted(pref)}")


def eval_rule(fn, rows, name):
    P = sum(r["y"] for r in rows)
    sel = [r for r in rows if fn(r)]
    if not sel:
        print(f"  {name:38s} selects 0"); return
    tp = sum(r["y"] for r in sel)
    prec = tp / len(sel); rec = tp / P if P else 0
    base = P / len(rows)
    print(f"  {name:38s} sel={len(sel):4d} tp={tp:3d} prec={prec:.3f} recall={rec:.3f} lift={prec/base:.2f} (base={base:.3f})")


print("\n=== RULE: uri_host in preferred set ===")
rule = lambda r: r["uri_host"] in pref
print(" IN-SAMPLE (train):")
eval_rule(rule, train, "host in preferred")
print(" OUT-OF-SAMPLE (test):")
eval_rule(rule, test, "host in preferred")

print("\n=== RULE: host in preferred AND has_desc ===")
rule2 = lambda r: r["uri_host"] in pref and r["has_desc"]
eval_rule(rule2, train, "train: host&has_desc")
eval_rule(rule2, test, "test:  host&has_desc")

print("\n=== RULE: host in preferred AND desc_len>=20 ===")
rule3 = lambda r: r["uri_host"] in pref and (r["desc_len"] or 0) >= 20
eval_rule(rule3, train, "train: host&desc>=20")
eval_rule(rule3, test, "test:  host&desc>=20")

# whole-dataset (in-sample, all) for the preferred rule for reference
print("\n=== Preferred-host rule on FULL labeled set (in-sample) ===")
eval_rule(rule, allrows, "host in preferred (all)")
eval_rule(rule2, allrows, "host&has_desc (all)")
