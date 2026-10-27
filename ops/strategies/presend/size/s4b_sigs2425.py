#!/usr/bin/env python3
"""SIZE study step 4b: for AMS r24/r25 (REPLAY_065 data, read-only), the other wallets' FAILED buys with a slippage error
(6002 / 6042) inside each position's span that REPLAY_065 did not fetch. Writes /home/moiz/sniper-data/presend_size/sigs_2425.json"""
import sys, json, collections, re, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
CODE = re.compile(r'"Custom":(\d+)')
if __name__ == "__main__":
    D = core.Data()                                  # BASE = replay065 (r24/r25)
    PS, RG, RF = pickle.load(open(f"{core.BASE}/pos_cal.pkl", "rb"))
    sigs = {}; codes = collections.Counter()
    for p in PS + RG:
        for x in D.tape[p.mint]["fails"]:
            s, i, sig, err, signer = x[0], x[1], x[2], x[3], x[4]
            if (s, i) <= p.buy_pos or s > p.end_slot or signer in OURS: continue
            m = CODE.search(err); c = int(m.group(1)) if m else None; codes[c] += 1
            if c in (6002, 6042, 6003) and sig not in D.args: sigs[sig] = p.mint
    print(codes.most_common(8)); print("new sigs", len(sigs))
    json.dump([[s, m] for s, m in sigs.items()], open("/home/moiz/sniper-data/presend_size/sigs_2425.json", "w"))
