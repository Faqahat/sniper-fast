#!/usr/bin/env python3
# Label EVERY dip trigger as direct (top-level pump sell, readable from shreds) or routed, from the collector's own raw rows
# (progs = all programs the tx invoked), and check the rule against the RPC truth (trig_tx.jsonl).
# Rule: direct iff the tx invokes no program outside a whitelist of non-routing programs (learned below, from the truth set).
# -> direct_flags.json {"mint|age": 1/0} for dipcv.py (DIRECT_FILE)
# usage: python3 -I direct_rule.py trig_sigs_all.jsonl trig_progs_all.jsonl trig_tx.jsonl direct_flags.json
import sys, json, collections
EV = [json.loads(l) for l in open(sys.argv[1])]
PG = {}
for l in open(sys.argv[2]):
    r = json.loads(l); PG[r["sig"]] = r
TX = {}
for l in open(sys.argv[3]):
    r = json.loads(l)
    if r.get("kind") in ("top", "routed"): TX[r["sig"]] = r["kind"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
# programs seen in truth-direct txs vs truth-routed txs
cd, cr = collections.Counter(), collections.Counter(); nd = nr = 0
for s, k in TX.items():
    if s not in PG or not PG[s].get("progs"): continue
    ps = set(PG[s]["progs"]) - {PUMP}
    if k == "top": nd += 1; cd.update(ps)
    else: nr += 1; cr.update(ps)
print(f"truth with raw rows: direct {nd}, routed {nr}")
print("programs in DIRECT txs (share of direct, share of routed):")
for p, c in cd.most_common(25): print(f"   {p[:44]:44s} {c / nd:6.1%} {cr[p] / max(nr, 1):6.1%}")
# whitelist: programs present in >=1% of direct txs and at most 3x as common (relative) in routed ones, or known infrastructure
KNOWN = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
         "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
         "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"}
WL = set(KNOWN) | {p for p, c in cd.items() if c / nd >= 0.01 and cr[p] / max(nr, 1) <= 3 * c / nd}
print("whitelist extra:", sorted(p[:12] for p in WL - KNOWN))
def rule(s):
    g = PG.get(s)
    if not g or not g.get("progs"): return None
    return int(not (set(g["progs"]) - {PUMP} - WL))
cm = collections.Counter()
for s, k in TX.items():
    v = rule(s)
    if v is not None: cm[(k, v)] += 1
tot = sum(cm.values())
print(f"rule vs truth: direct->1 {cm[('top', 1)]}, direct->0 {cm[('top', 0)]}, routed->0 {cm[('routed', 0)]}, routed->1 {cm[('routed', 1)]}; accuracy {(cm[('top', 1)] + cm[('routed', 0)]) / max(tot, 1):.1%}")
flags = {}; miss = 0
for e in EV:
    if not e.get("sig"): continue
    v = TX.get(e["sig"])
    v = (1 if v == "top" else 0) if v else rule(e["sig"])
    if v is None: miss += 1; continue
    flags[f'{e["m"]}|{e["age"]}'] = v
json.dump(flags, open(sys.argv[4], "w"))
print("events", len(EV), "labelled", len(flags), "direct share", round(sum(flags.values()) / max(len(flags), 1), 3), "unlabelled", miss)
