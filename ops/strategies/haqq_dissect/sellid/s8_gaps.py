#!/usr/bin/env python3
"""SELLID step 8 (read-only): (a) where in the block his 247/248 sells land relative to the outside trade right before them
(same slot? tx-index gap) vs where his dump-BUYS land relative to the dump (a known reactive action, b1.pkl); (b) the wallets whose
SELLS precede 248's sells (s2/s4 'co-sellers'): same slot or earlier slot, and do they trade the same dumps (common cause)?
Out: sellid/s8.txt"""
import pickle, json, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); S = Z["sells"]; LOTS = Z["lots"]
ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json")); idm = {k: i for i, k in enumerate(ids)}
B1 = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/bots/b1.pkl", "rb"))
bins = [1, 2, 3, 6, 11, 21, 51, 101, 201, 10 ** 6]
def hist(v):
    h = np.histogram(v, bins)[0]; return " ".join(f"{a}-{b - 1}:{x / max(len(v), 1):.3f}" for a, b, x in zip(bins[:-1], bins[1:], h))
P("# Where his sells land relative to the trade before them (MEASURED)")
for c in (247, 248):
    v = [s for s in S if s["code"] == c]
    prev_any = []; prev_buy212 = []; same_any = 0; n_any = 0; same_b = 0; n_b = 0
    for s in v:
        if len(s["w_us"]):
            j = int(np.argmin(s["w_dcc"])); n_any += 1
            if s["w_ds"][j] == 0: same_any += 1; prev_any.append(int(s["w_di"][j]))
        b = np.flatnonzero(s["w_bu"] & (s["w_dcc"] <= 212))
        if len(b):
            j = b[np.argmin(s["w_dcc"][b])]; n_b += 1
            if s["w_ds"][j] == 0: same_b += 1; prev_buy212.append(int(s["w_di"][j]))
    P(f"\n## bot {c}: {len(v):,} sells")
    P(f"- nearest outside trade before the sell (within 3 slots): {n_any:,}; in the SAME slot {same_any / max(n_any, 1):.3f}; same-slot tx-index gap: {hist(prev_any)}")
    P(f"- sells with an outside BUY <= 212 ms before: {n_b:,} ({n_b / len(v):.3f}); that buy in the same slot {same_b / max(n_b, 1):.3f}; same-slot index gap: {hist(prev_buy212)}")
    bb = [r for r in B1 if r["code"] == c and r["dump"] and r["d_slots"] == 0 and r["d_idx"] is not None]
    P(f"- reference, his dump-BUYS in the dump's slot ({len(bb):,}): index gap dump->buy: {hist([r['idx'] - r['d_idx'] for r in bb])}")
# co-sellers
P("\n## Co-sellers: wallets whose SELLS precede 248/247 sells within 212 ms most above chance (s2 top), how they relate to him")
U = dict(np.load(f"{OUT}/s2_units.npz"))
for w in ("HXHoJwF5", "Fau6ESkZ", "FfbyDLrG", "3qZ3RTQs", "3iawEZGf", "HtJ9i3Bs", "8KUYGivN", "7dMDTT4j", "2fg5QD1e"):
    wid = [i for i, x in enumerate(ids) if x.startswith(w)]
    if not wid: continue
    wid = wid[0]
    m = U["us"] == wid
    sel = m & (U["gap"] <= 212)
    # does this wallet BUY the same dumps as him? (a buy within 2 s before his entry on his lots)
    nl = 0; same = 0
    for l in LOTS:
        nl += 1
    lots_with = sum(1 for l in LOTS if (l["p_us"] == wid).any())
    lots_buy_early = sum(1 for l in LOTS if ((l["p_us"] == wid) & l["p_bu"] & (l["p_dcc"] <= 400)).any())
    P(f"- {ids[wid][:8]} ({ids[wid]}): trades while his lots open {m.sum():,} (buys {int((m & U['bu']).sum())}, sells {int((m & ~U['bu']).sum())}); "
      f"followed by his sell <=212 ms {sel.sum()} (buy-side {int((sel & U['bu']).sum())}, sell-side {int((sel & ~U['bu']).sum())}); present in {lots_with:,} of his lots, "
      f"buys within 400 ms after his entry in {lots_buy_early:,}")
open(f"{OUT}/s8.txt", "w").write("\n".join(out) + "\n")
