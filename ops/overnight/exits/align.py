#!/usr/bin/env python3
# READ-ONLY, offline. Align every sell of the wallet with the market path of the token (collector phase-A rows, both runs):
# what happened before it (dev = launch signer + creator; its sells, sold fraction and cumulative sold share; create-bundle /
# create-slot buyers ("group") sells; big trades), where the price was vs entry and vs the running peak, and lags in slots.
# Also, for every dev sell during the hold, whether (and how fast) the wallet sold after it.
# usage: python3 -I align.py  -> align.json
import sys, os, json, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

ALL = {w: json.load(open(f"{EXITS}/roundtrips_{w}.json"))["tokens"] for w in WALLETS}
mints = {r["mint"] for R in ALL.values() for r in R}
LA = load_launches(mints)
out = []
for w, R in ALL.items():
    W = WALLETS[w]
    for r in R:
        m = r["mint"]; la = LA.get(m)
        if not la: continue
        tr, xs = trades_of(m)
        if not tr: continue
        pos = {t["sig"]: k for k, t in enumerate(tr) if t["user"] == W}
        legs = [l for l in r["legs"] if l["side"] in ("buy", "sell")]
        miss = [l for l in legs if l["sig"] not in pos]
        cov = dict(n_legs=len(legs), missing=len(miss), last_slot=tr[-1]["s"])
        if miss:
            out.append(dict(w=w, mint=m, coverage=cov)); continue
        dev = {la.get("user"), la.get("creator")} - {None}
        S0 = la["slot"]; ci = la.get("idx")
        kb = pos[legs[0]["sig"]]; t_buy = tr[kb]
        glued = set(); prev = ci
        for t in tr:
            if t["s"] < S0: continue
            if t["s"] > S0: break
            if t["sig"] == la.get("sig"): continue
            if t["buy"] and prev is not None and t["i"] in (prev, prev + 1) and t["user"] not in dev: glued.add(t["user"]); prev = t["i"]
        early = {t["user"] for t in tr[:kb] if t["s"] == S0 and t["buy"]} - dev - {W}
        grp = glued | early
        hold = collections.defaultdict(float); bought = collections.defaultdict(float)
        entry = r["entry_px"]; peak = 0.0; recs = []; own_prev = None; own_prev_k = None
        dev_events = []   # dev sells after our buy: (k, slot, frac, cum)
        for k, t in enumerate(tr):
            p_before = (tr[k - 1]["vsol"] / tr[k - 1]["vtok"]) if k > 0 else None
            u = t["user"]
            if u == W and not t["buy"] and k > kb:
                held = hold[W]
                ds = [e for e in dev_events if e["k"] < k]
                last_dev = ds[-1] if ds else None
                new_dev = [e for e in ds if own_prev_k is None or e["k"] > own_prev_k]
                gs = [x for x in tr[kb:k] if x["user"] in grp and not x["buy"]]
                last_g = gs[-1] if gs else None
                win = [x for x in tr[max(kb, k - 300):k] if x["s"] >= t["s"] - 3 and x["user"] != W]
                recs.append(dict(k=k, slot=t["s"], idx=t["i"], bt=t["bt"], dslot=t["s"] - t_buy["s"], dprev=(t["s"] - own_prev) if own_prev is not None else None,
                                 sig=t["sig"], frac=t["tok"] / held if held > 0 else None, sol=t["sol"] / 1e9,
                                 mult_pre=p_before / entry if p_before else None, peak_mult=peak / entry if peak else None,
                                 dd=(1 - p_before / peak) if (p_before and peak) else None,
                                 last_dev=dict(dslot=t["s"] - last_dev["slot"], dk=k - last_dev["k"], frac=last_dev["frac"], cum=last_dev["cum"]) if last_dev else None,
                                 new_dev=[dict(dslot=t["s"] - e["slot"], frac=e["frac"], cum=e["cum"]) for e in new_dev],
                                 dev_cum=(1 - (sum(hold[d] for d in dev) / max(1.0, sum(bought[d] for d in dev)))) if sum(bought[d] for d in dev) > 0 else None,
                                 last_grp=dict(dslot=t["s"] - last_g["s"], sol=last_g["sol"] / 1e9) if last_g else None,
                                 win_sell_sol=sum(x["sol"] for x in win if not x["buy"]) / 1e9, win_buy_sol=sum(x["sol"] for x in win if x["buy"]) / 1e9))
                own_prev = t["s"]; own_prev_k = k
            if u in dev and not t["buy"] and k > kb:
                dh = sum(hold[d] for d in dev); db = sum(bought[d] for d in dev)
                frac = t["tok"] / dh if dh > 0 else None
                cum = 1 - (dh - t["tok"]) / db if db > 0 else None
                dev_events.append(dict(k=k, slot=t["s"], frac=frac, cum=cum, sol=t["sol"] / 1e9))
            if t["buy"]: hold[u] += t["tok"]; bought[u] += t["tok"]
            else: hold[u] = max(0.0, hold[u] - t["tok"])
            if k >= kb and (u != W or t["buy"]): peak = max(peak, t["vsol"] / t["vtok"])
        # reaction to each dev sell during our hold: next own sell, slots after
        last_own = recs[-1]["k"] if recs else kb
        react = []
        for e in dev_events:
            if e["k"] > last_own: break
            nxt = next((s for s in recs if s["k"] > e["k"]), None)
            react.append(dict(slot=e["slot"], frac=e["frac"], cum=e["cum"], sol=e["sol"], next_own_dslot=(nxt["slot"] - e["slot"]) if nxt else None,
                              next_own_frac=nxt["frac"] if nxt else None))
        out.append(dict(w=w, mint=m, coverage=cov, creator=la.get("creator"), signer=la.get("user"), create_slot=S0, create_idx=ci,
                        buy_slot=t_buy["s"], buy_idx=t_buy["i"], buy_bt=t_buy["bt"], buy_pos_in_path=kb, entry_px=entry, pnl=r["pnl"], buy_sol=r["buy_sol"],
                        n_glued=len(glued), n_early=len(early), sells=recs, dev_sells=react, n_path=len(tr)))
json.dump(out, open(f"{EXITS}/align.json", "w"))
ok = [o for o in out if not o["coverage"]["missing"]]
print("tokens with launch info:", len(out), "| full path coverage:", len(ok), "| missing legs:", [(o["w"], o["mint"][:6], o["coverage"]) for o in out if o["coverage"]["missing"]][:10])
