import json, math
from collections import Counter
from urllib.parse import urlparse

POSM = json.load(open("/root/sel2/pos_meta.json"))
NEGM = json.load(open("/root/sel2/neg_meta.json"))
POSF = json.load(open("/root/sel/pos_feat.json"))
NEGF = json.load(open("/root/sel/neg_feat.json"))


def host(uri):
    try:
        return urlparse(uri).netloc.lower() or "?"
    except Exception:
        return "?"


BUYSLOT = json.load(open("/root/sel/pos.json")).get("buyslot", {})


def build(metad, featd, label, slotfb=None):
    slotfb = slotfb or {}
    rows = []
    for m, mv in metad.items():
        # include no_uri_json too: it still has uri/uri_host (only socials JSON missing)
        if mv.get("status") not in ("ok", "no_uri_json"):
            continue
        if not mv.get("uri"):
            continue
        fv = featd.get(m, {})
        slot = fv.get("create_slot") or slotfb.get(m)
        if not slot:
            continue
        rows.append({"mint": m, "y": label, "create_slot": slot,
                     "has_meta_json": 1 if mv.get("status") == "ok" else 0,
                     "uri_host": mv.get("uri_host") or host(mv.get("uri", "")),
                     "has_desc": 1 if mv.get("has_desc") else 0,
                     "desc_len": mv.get("desc_len", 0) or 0,
                     "dev_buy_sol": fv.get("dev_buy_sol"),
                     "total_bundled_sol": fv.get("total_bundled_sol"),
                     "n_cobundlers": fv.get("n_cobundlers")})
    return rows


pos = build(POSM, POSF, 1, BUYSLOT)
neg = build(NEGM, NEGF, 0)
pslots = sorted(r["create_slot"] for r in pos)
lo, hi = pslots[0], pslots[-1]
neg = [r for r in neg if lo <= r["create_slot"] <= hi]
allrows = sorted(pos + neg, key=lambda r: r["create_slot"])
P, N = len(pos), len(neg)
base = P / (P + N)
print(f"DATASET: pos={P}  neg(in-window)={N}  sampled_base_rate={base:.3f}")
print(f"(coverage of his buys: {P}/361 pos_mints resolved to ok-metadata & slot)\n")

# ---------------- full-sample host table ----------------
ph = Counter(r["uri_host"] for r in pos); nh = Counter(r["uri_host"] for r in neg)
print("=== URI-HOST (launch-tool fingerprint) full labeled set ===")
print(f"{'host':30s}{'his':>5s}{'his%':>7s}{'neg':>5s}{'neg%':>7s}{'lift':>7s}")
for h in sorted(set(ph) | set(nh), key=lambda x: -(ph[x] + nh[x])):
    if ph[h] + nh[h] < 3:
        continue
    pp = ph[h] / P; npp = nh[h] / N
    lift = pp / npp if npp else float('inf')
    ls = f"{lift:.2f}" if lift != float('inf') else "inf"
    print(f"{h[:30]:30s}{ph[h]:>5d}{pp:>7.3f}{nh[h]:>5d}{npp:>7.3f}{ls:>7s}")

# ---------------- TIME SPLIT ----------------
cut = int(len(allrows) * 0.6)
ss = allrows[cut]["create_slot"]
train = [r for r in allrows if r["create_slot"] < ss]
test = [r for r in allrows if r["create_slot"] >= ss]
print(f"\n=== TIME SPLIT @slot {ss}: train n={len(train)} pos={sum(r['y'] for r in train)} | test n={len(test)} pos={sum(r['y'] for r in test)} ===")


def eval_rule(fn, rows, name):
    Pn = sum(r["y"] for r in rows)
    sel = [r for r in rows if fn(r)]
    if not sel:
        print(f"  {name:34s} sel=0"); return None
    tp = sum(r["y"] for r in sel)
    prec = tp / len(sel); rec = tp / Pn if Pn else 0
    b = Pn / len(rows)
    print(f"  {name:34s} sel={len(sel):4d} tp={tp:3d} prec={prec:.3f} rec={rec:.3f} lift={prec/b:.2f}")
    return prec, rec, prec / b


# learn WHITELIST on train (his>=4 & lift>=1.3); BLACKLIST = hosts with >=5 negs and 0 his
trph = Counter(r["uri_host"] for r in train if r["y"] == 1)
trnh = Counter(r["uri_host"] for r in train if r["y"] == 0)
trP = sum(r["y"] for r in train); trN = len(train) - trP
white = set()
black = set()
for h in set(trph) | set(trnh):
    pp = trph[h] / trP if trP else 0
    npp = trnh[h] / trN if trN else 0
    lift = pp / npp if npp else (99 if pp else 0)
    if trph[h] >= 4 and lift >= 1.3:
        white.add(h)
    if trph[h] == 0 and trnh[h] >= 4:
        black.add(h)
print(f"\nLearned on TRAIN only:")
print(f"  WHITELIST (preferred): {sorted(white)}")
print(f"  BLACKLIST (never his): {sorted(black)}")

print("\n--- WHITELIST rule (host in preferred) ---")
print(" train:"); eval_rule(lambda r: r["uri_host"] in white, train, "host in whitelist")
print(" TEST :"); eval_rule(lambda r: r["uri_host"] in white, test, "host in whitelist")

print("\n--- BLACKLIST rule (host NOT in blacklist) = keep everything except known-avoided tools ---")
print(" train:"); eval_rule(lambda r: r["uri_host"] not in black, train, "host not in blacklist")
print(" TEST :"); eval_rule(lambda r: r["uri_host"] not in black, test, "host not in blacklist")

print("\n--- WHITELIST AND has_desc ---")
print(" train:"); eval_rule(lambda r: r["uri_host"] in white and r["has_desc"], train, "whitelist & has_desc")
print(" TEST :"); eval_rule(lambda r: r["uri_host"] in white and r["has_desc"], test, "whitelist & has_desc")

# ---------------- precision at target recall (full in-sample, score=host his-lift) ----------------
# build a host-lift score on full set, rank, report precision at recall .5 and .7
hostlift = {}
for h in set(ph) | set(nh):
    pp = ph[h] / P; npp = nh[h] / N
    hostlift[h] = pp / npp if npp else (99 if pp else 0)
scored = sorted(allrows, key=lambda r: -hostlift.get(r["uri_host"], 0))
print("\n=== Precision at target recall (full-sample, rank by host his-lift) ===")
cum_tp = 0
seen = 0
targets = {0.5: None, 0.7: None, 0.9: None}
for r in scored:
    seen += 1
    cum_tp += r["y"]
    rec = cum_tp / P
    for t in targets:
        if targets[t] is None and rec >= t:
            targets[t] = (seen, cum_tp, cum_tp / seen, (cum_tp / seen) / base)
for t in sorted(targets):
    v = targets[t]
    if v:
        print(f"  recall>={t}: sel={v[0]} tp={v[1]} precision={v[2]:.3f} lift={v[3]:.2f}")
print(f"\n  (sampled base rate {base:.3f}; TRUE base rate ~0.08, so real precision ~= lift*0.08)")
