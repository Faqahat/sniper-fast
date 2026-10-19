import json, itertools
from collections import Counter

F = json.load(open("/root/sep/features.json"))
rows = sorted(F.values(), key=lambda r: r["slot"])

# reject predicates: return True => filter the token OUT (predict LOSER)
def P(name, fn):
    return (name, fn)

def name_lower(r):
    nm = r.get("name")
    if nm is None:
        return True  # unparseable create => treat as reject
    return nm.islower()

PREDS = [
    P("name_all_lowercase_or_missing", name_lower),
    P("dev_round_N.0_SOL",        lambda r: r["dev"] % 1_000_000_000 == 0),
    P("dev_eq_3.0",               lambda r: r["dev"] == 3_000_000_000),
    P("dev_lt_1.0",               lambda r: r["dev"] < 1_000_000_000),
    P("host_not_ipfs.io",         lambda r: r.get("uri_host") != "ipfs.io"),
    P("no_space_in_name",         lambda r: not r.get("name_has_space", False)),
    P("symbol_not_upper",         lambda r: not r.get("symbol_upper", False)),
    P("name_len<=5",              lambda r: (r.get("name_len") or 0) <= 5),
    P("desc_len<=5",              lambda r: (r.get("desc_len") or 0) <= 5),
    P("peek_slot0_1<=5",          lambda r: (r.get("peek_n_slot0_1") or 0) <= 5),  # PEEK
]

def evaluate(keep_fn, subset):
    """keep_fn(r)->True means we KEEP (predict winner). Score vs WIN/LOSE."""
    kept = [r for r in subset if keep_fn(r)]
    rej  = [r for r in subset if not keep_fn(r)]
    kw = sum(1 for r in kept if r["label"] == "WIN")
    kl = sum(1 for r in kept if r["label"] == "LOSE")
    km = sum(1 for r in kept if r["label"] == "MID")
    rw = sum(1 for r in rej if r["label"] == "WIN")
    rl = sum(1 for r in rej if r["label"] == "LOSE")
    rm = sum(1 for r in rej if r["label"] == "MID")
    totW = kw + rw; totL = kl + rl
    prec = kw / (kw + kl) if (kw + kl) else float("nan")
    recall = kw / totW if totW else float("nan")
    loser_removal = rl / totL if totL else float("nan")
    return dict(kw=kw, kl=kl, km=km, rw=rw, rl=rl, rm=rm, prec=prec, recall=recall, lrem=loser_removal)

WL = [r for r in rows if r["label"] in ("WIN", "LOSE")]
baseW = sum(1 for r in WL if r["label"] == "WIN")
baseL = sum(1 for r in WL if r["label"] == "LOSE")
print(f"BASELINE band: WIN={baseW} LOSE={baseL} precision={baseW/(baseW+baseL):.3f}\n")

# ---- single predicates ----
print("===== SINGLE REJECT RULES (keep = NOT pred) =====")
print(f"{'rule':<34} {'keptW':>5} {'keptL':>5} {'prec':>5} {'recall':>6} {'Lremoved':>8}")
singles = []
for nm, fn in PREDS:
    e = evaluate(lambda r, fn=fn: not fn(r), WL)
    singles.append((nm, fn, e))
    print(f"{nm:<34} {e['kw']:>5} {e['kl']:>5} {e['prec']:>5.2f} {e['recall']:>6.2f} {e['lrem']:>8.2f}")

# ---- pairs (reject if EITHER true) ----
print("\n===== PAIR REJECT RULES (keep = NOT(a or b)) =====")
print(f"{'rule':<52} {'keptW':>5} {'keptL':>5} {'prec':>5} {'recall':>6} {'Lrem':>5}")
results = []
for (na, fa), (nb, fb) in itertools.combinations(PREDS, 2):
    e = evaluate(lambda r, fa=fa, fb=fb: not (fa(r) or fb(r)), WL)
    results.append((f"{na} OR {nb}", e))
# rank by (keptW high, keptL low): maximize keptW - 2*keptL
results.sort(key=lambda x: (x[1]["kw"] - 2 * x[1]["kl"]), reverse=True)
for nm, e in results[:12]:
    print(f"{nm:<52} {e['kw']:>5} {e['kl']:>5} {e['prec']:>5.2f} {e['recall']:>6.2f} {e['lrem']:>5.2f}")

# ======== TEMPORAL OUT-OF-SAMPLE ========
WL_sorted = sorted(WL, key=lambda r: r["slot"])
half = len(WL_sorted) // 2
train = WL_sorted[:half]
test = WL_sorted[half:]
def cc(sub):
    return Counter(r["label"] for r in sub)
print(f"\n===== TEMPORAL SPLIT (by slot) =====")
print(f"TRAIN n={len(train)} {dict(cc(train))}  | TEST n={len(test)} {dict(cc(test))}")
split_slot = test[0]["slot"]
print(f"train slots <= {train[-1]['slot']} ; test slots >= {split_slot}")

def rule_report(label, keep_fn):
    et = evaluate(keep_fn, train)
    ev = evaluate(keep_fn, test)
    print(f"\n[{label}]")
    print(f"  TRAIN keptW={et['kw']} keptL={et['kl']} prec={et['prec']:.2f} recall={et['recall']:.2f} Lrem={et['lrem']:.2f}")
    print(f"  TEST  keptW={ev['kw']} keptL={ev['kl']} prec={ev['prec']:.2f} recall={ev['recall']:.2f} Lrem={ev['lrem']:.2f}")

rule_report("R1: keep if name NOT all-lowercase (and parseable)",
            lambda r: not name_lower(r))
rule_report("R2: keep if dev NOT exact N.0 SOL",
            lambda r: r["dev"] % 1_000_000_000 != 0)
rule_report("R3: keep if (name not lowercase) AND dev>=1.0",
            lambda r: (not name_lower(r)) and r["dev"] >= 1_000_000_000)
rule_report("R4: keep if (name not lowercase) AND NOT(dev==3.0 AND name_len<=5)",
            lambda r: (not name_lower(r)) and not (r["dev"] == 3_000_000_000 and (r.get("name_len") or 0) <= 5))
rule_report("R5: keep if host==ipfs.io",
            lambda r: r.get("uri_host") == "ipfs.io")
rule_report("R6: keep if dev NOT round-N.0 AND name not lowercase",
            lambda r: (r["dev"] % 1_000_000_000 != 0) and (not name_lower(r)))

# full apply of R1 on the whole band incl MID
print("\n===== R1 applied to FULL band (incl MID) =====")
allrows = rows
kept = [r for r in allrows if not name_lower(r)]
rej = [r for r in allrows if name_lower(r)]
print("KEEP:", Counter(r["label"] for r in kept))
print("REJECT:", Counter(r["label"] for r in rej))
print("rejected mints:", [(r["mint"][:8], r["label"], r.get("name")) for r in rej])
print("kept-but-LOSE mints:", [(r["mint"][:8], r.get("name"), r["dev"]/1e9) for r in kept if r["label"] == "LOSE"])
