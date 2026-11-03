"""Arm-time chain features (only trades up to and including the whale's trigger trade)."""
import json, gzip, collections
from feat import *
CH = json.load(gzip.open("/home/moiz/sniper-data/presend_losses/chain_trades.json.gz", "rt"))
SUP = 1e15
def cfeats(r):
    a = r["arm"]; tr = CH.get(r["mint"])
    if not a or not tr: return None
    ts, ti = a["slot"], None
    # trigger trade: whale buy in trigger slot
    pre = [x for x in tr if x[0] < ts or (x[0] == ts and x[3] == a["wallet"] and x[5]) or (x[0] == ts)]
    # cut at the whale's trigger buy (the first whale buy in the trigger slot)
    cut = None
    for k, x in enumerate(tr):
        if x[0] == ts and x[3] == a["wallet"] and x[5]: cut = k; break
    if cut is None: return None
    pre = tr[:cut + 1]
    s0 = tr[0][0]
    bal = collections.Counter(); first = {}
    for x in pre:
        bal[x[3]] += x[7] if x[5] else -x[7]; first.setdefault(x[3], x[0])
    creator = tr[0][3] if tr[0][0] == s0 else None
    others = {w: b for w, b in bal.items() if w != a["wallet"] and b > 0}
    big = {w: b for w, b in others.items() if b >= 0.03 * SUP}
    same_slot = [x for x in pre if x[0] == ts and x[3] != a["wallet"]]
    early = [w for w, s in first.items() if s <= s0 + 1 and w != a["wallet"]]
    early_hold = sum(bal[w] for w in early if bal[w] > 0) / SUP * 100
    return dict(n_pre=len(pre), buyers_pre=len({x[3] for x in pre if x[5]}), big_n=len(big), big_pct=sum(big.values()) / SUP * 100,
                top_other_pct=max(others.values(), default=0) / SUP * 100, others_pct=sum(others.values()) / SUP * 100,
                same_slot_n=len(same_slot), same_slot_buy_sol=sum(x[6] for x in same_slot if x[5]) / 1e9,
                early_hold_pct=early_hold, creator_pct=bal.get(creator, 0) / SUP * 100 if creator else None,
                whale_prev_pct=(bal[a["wallet"]] - [x for x in pre if x[3] == a["wallet"]][-1][7]) / SUP * 100,
                age_slots_chain=ts - s0)
if __name__ == "__main__":
    n = m = 0
    for run in RUNS:
        for r in load(run):
            n += 1; c = cfeats(r); m += c is not None
    print("covered", m, "of", n)
