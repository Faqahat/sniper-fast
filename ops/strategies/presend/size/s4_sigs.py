#!/usr/bin/env python3
"""SIZE study step 4: the signatures whose slippage limits we need (read-only, offline): for every live position of r26-r28
(pre-send + regular), every other wallet's trade after our buy up to the position's end slot, and every other wallet's FAILED
pump tx on the token in the same span with a slippage error (6002 too much SOL / 6042 below min tokens out / 6003 too little SOL).
Writes /home/moiz/sniper-data/presend_size/sigs_hold.json ([[sig, mint], ...]) for r065's fetch.py (read-only RPC)."""
import sys, json, collections, re
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core
BASE = "/home/moiz/sniper-data/presend_size"
core.BASE = BASE
import positions as PO
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
CODE = re.compile(r'"Custom":(\d+)')

def code_of(err):
    m = CODE.search(err); return int(m.group(1)) if m else None

if __name__ == "__main__":
    D = core.Data()
    PS = PO.presend_positions(D); RG, RF = PO.regular_positions(D)
    print("positions: pre-send", collections.Counter(p.run for p in PS), "regular", collections.Counter(p.run for p in RG), "reg failed", len(RF))
    sigs = {}; codes = collections.Counter(); nf = 0
    for p in PS + RG:
        for r in p.rows:
            if r["kind"] == "trade": sigs[r["tr"]["sig"]] = p.mint
        for x in D.tape[p.mint]["fails"]:
            s, i, sig, err, signer = x[0], x[1], x[2], x[3], x[4]
            if (s, i) <= p.buy_pos or s > p.end_slot or signer in OURS: continue
            c = code_of(err); codes[c] += 1
            if c in (6002, 6042, 6003): sigs[sig] = p.mint; nf += 1
    print("other wallets' failed txs in spans by code (top):", codes.most_common(10))
    json.dump([[s, m] for s, m in sigs.items()], open(f"{BASE}/sigs_hold.json", "w"))
    print("sigs", len(sigs), "of which failed slippage", nf)
