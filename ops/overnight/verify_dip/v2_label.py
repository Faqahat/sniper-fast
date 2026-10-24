#!/usr/bin/env python3
# Direct/routed labels for event files that carry the trigger sig ("tsig", from v2_mods/*_sig.py builds), made exactly like
# dipshadow/direct_rule.py: RPC truth (trig_tx.jsonl) where fetched, else the whitelist rule on the collector's `progs`
# (whitelist re-derived here with direct_rule.py's own formula). Missing progs are scanned from the raw chunks. Local files only.
# usage: python3 -I v2_label.py out_labels.json ev1.jsonl.gz [ev2.jsonl.gz ...]
import sys, os, json, gzip, glob, collections
from multiprocessing import Pool
SH = "/home/moiz/sniper/ops/overnight/dipshadow"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
FILES = sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261021_2207/txs/*.jsonl.gz") + glob.glob("/home/moiz/sniper-data/collect/run_20261022_1543/txs/*.jsonl.gz"))
NEED = set()
def scan(f):
    out = []
    try:
        for line in gzip.open(f, "rt"):
            a = line.find('"sig":"')
            if a < 0: continue
            sg = line[a + 7:line.find('"', a + 7)]
            if sg in NEED: out.append((sg, json.loads(line).get("progs")))
    except (EOFError, OSError): pass
    return out
if __name__ == "__main__":
    out_path = sys.argv[1]; evs = sys.argv[2:]
    TX = {}
    for l in open(f"{SH}/trig_tx.jsonl"):
        r = json.loads(l)
        if r.get("kind") in ("top", "routed"): TX[r["sig"]] = r["kind"]
    PG = {}
    for l in open(f"{SH}/trig_progs_all.jsonl"):
        r = json.loads(l); PG[r["sig"]] = r.get("progs")
    # whitelist, as in direct_rule.py
    cd, cr = collections.Counter(), collections.Counter(); nd = nr = 0
    for s, k in TX.items():
        if not PG.get(s): continue
        ps = set(PG[s]) - {PUMP}
        if k == "top": nd += 1; cd.update(ps)
        else: nr += 1; cr.update(ps)
    KNOWN = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
             "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
             "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"}
    WL = set(KNOWN) | {p for p, c in cd.items() if c / nd >= 0.01 and cr[p] / max(nr, 1) <= 3 * c / nd}
    print("whitelist size", len(WL), "extra", sorted(p[:12] for p in WL - KNOWN))
    rows = []
    for f in evs:
        for l in gzip.open(f, "rt"):
            r = json.loads(l); rows.append((f'{r["m"]}|{r["age"]}', r["tsig"]))
    NEED = {s for _, s in rows if s not in TX and s not in PG}
    print("events", len(rows), "sigs needing a raw-chunk scan", len(NEED), flush=True)
    if NEED:
        with Pool(int(os.environ.get("NPROC", "6"))) as p:
            for res in p.imap_unordered(scan, FILES):
                for sg, pr in res: PG[sg] = pr
    lab = {}; src = collections.Counter()
    for key, s in rows:
        if s in TX: lab[key] = 1 if TX[s] == "top" else 0; src["truth"] += 1
        elif PG.get(s): lab[key] = int(not (set(PG[s]) - {PUMP} - WL)); src["rule"] += 1
        else: src["none"] += 1
    json.dump(lab, open(out_path, "w"))
    print("labelled", len(lab), dict(src), "direct share", round(sum(lab.values()) / max(len(lab), 1), 3))
