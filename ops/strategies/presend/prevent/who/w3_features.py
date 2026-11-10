#!/usr/bin/env python3
"""WHO step 3 [MEASURED from the tapes]: per window (live + paper) the holder state at arm time, the token's creator / launch bundle,
the trades between arm and our fill, and (live fills) every wallet that sold inside our hold with its ROLE at arm time.
Arm cut: T2 = trades up to and including the trigger trade (slot, idx); re-arm = trades in slots < arm slot (dump + 3).
In-hold sellers: market tape trades after our buy (fill slot, idx) and before our sell land (slot, idx), not ours.
Out: /home/it/sniper-data/prevent/who/feats.pkl  (list, same order as windows.pkl) + bots.json"""
import json, pickle, re, bisect, collections
import numpy as np

D = "/home/it/sniper-data/prevent/who"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
SUP = 1e15
RIVAL_PFX = ["8yYMhuYo", "dKMjeGJ4", "haqqiUUX", "HkQ7hMjy", "DYXDDrZC", "CvHEVC7S", "6VzXcLk9", "CZ77onJz"]


def bots(users):
    coh = json.load(open("/home/it/sniper-data/overnight/sel/cohort_train.json"))
    coh = {c if isinstance(c, str) else (c.get("wallet") or c.get("w")) for c in coh}
    cand = set(re.findall(r"gmgn\.ai/sol/address/([1-9A-HJ-NP-Za-km-z]{32,44})", open("/home/it/sniper/ops/snipers/CANDIDATES.md").read()))
    riv = {}
    cnt = collections.Counter(users)
    for p in RIVAL_PFX:
        m = [(cnt[u], u) for u in cnt if u.startswith(p)]
        if m: riv[p] = max(m)[1]
    return coh, cand, riv


def main():
    W = pickle.load(open(f"{D}/windows.pkl", "rb"))
    M = pickle.load(open(f"{D}/mints.pkl", "rb"))
    C = pickle.load(open(f"{D}/creates.pkl", "rb"))
    allu = []
    for rows in M.values(): allu.extend(r[8] for r in rows)
    coh, cand, riv = bots(allu)
    del allu
    botset = coh | cand | set(riv.values())
    json.dump({"cohort": len(coh), "candidates": len(cand), "rivals": riv, "n": len(botset)}, open(f"{D}/bots.json", "w"), indent=1)
    print("bots", len(coh), len(cand), riv, flush=True)
    keys = {m: [(r[0], r[1]) for r in rows] for m, rows in M.items()}
    F = []
    for n, w in enumerate(W):
        f = {"i": n}
        rows = M.get(w["mint"])
        if not rows: F.append(f); continue
        c = C.get(w["mint"])
        s0 = c[1] if c else rows[0][0]
        creator = c[0] if c else None
        f.update(s0=s0, creator=creator, has_create=c is not None, cbt=c[2] if c else None, mayhem=c[3] if c else None)
        ks = keys[w["mint"]]
        if w["kind"] == "rearm": kcut = bisect.bisect_left(ks, (w["arm_slot"], -1))
        else: kcut = bisect.bisect_right(ks, (w["trig_slot"], w["trig_idx"] if w["trig_idx"] is not None else 10 ** 9))
        f["tape_ok"] = rows[0][0] <= s0 + 1 or c is None
        bal = collections.defaultdict(int); first = {}; sold = collections.defaultdict(int); bought = collections.defaultdict(int)
        for r in rows[:kcut]:
            u = r[8]
            if r[3]:
                bal[u] += r[5]; bought[u] += r[5]
                if u not in first: first[u] = r[0]
            else: bal[u] -= r[5]; sold[u] += r[5]
        hold = {u: b / SUP * 100 for u, b in bal.items() if b > 0 and u not in OURS}
        f["hold"] = {u: p for u, p in hold.items() if p >= 0.3}
        f["first"] = {u: first.get(u) for u in f["hold"]}
        f["sold_before"] = {u: sold[u] / SUP * 100 for u in f["hold"] if sold[u] > 0}
        tw = w.get("wallet")
        f["trig_sold_before"] = sold.get(tw, 0) / SUP * 100 if tw else 0.0
        f["trig_first"] = first.get(tw)
        f["creator_pct"] = hold.get(creator, 0.0) if creator else 0.0
        f["n_trades_arm"] = kcut
        # the trades between arm and our fill slot (live fills) / to the window end (others): wallets that bought, their pct after
        end_slot = w.get("fill_slot") if w.get("filled") else (w.get("en_slot") or w["trig_slot"] + 12)
        kend = bisect.bisect_left(ks, (end_slot, -1))
        b2 = dict(bal); wb = {}
        for r in rows[kcut:kend]:
            u = r[8]
            if u in OURS: continue
            b2[u] = b2.get(u, 0) + (r[5] if r[3] else -r[5])
            if r[3]: wb[u] = b2[u] / SUP * 100
        f["win_buyers"] = wb
        if w.get("filled"):
            fs, fi = w["fill_slot"], w.get("fill_idx") or 0
            ss, si = (w["sell_slot"], w.get("sell_idx") or 0) if w.get("sell_slot") else (fs + 3, 0)
            ka = bisect.bisect_right(ks, (fs, fi)); kb = bisect.bisect_left(ks, (ss, si))
            sellers = collections.defaultdict(float); buyers_in = collections.defaultdict(float)
            for r in rows[ka:kb]:
                u = r[8]
                if u in OURS: continue
                if r[3]: buyers_in[u] += r[4] / 1e9
                else: sellers[u] += r[4] / 1e9
            # all trades by non-ours between the arm cut and our buy (incl. fill-slot trades before our buy)
            pre = collections.defaultdict(float)
            kf = bisect.bisect_left(ks, (fs, fi))
            for r in rows[kcut:kf]:
                if r[8] in OURS: continue
                if not r[3]: pre[r[8]] += r[4] / 1e9
            roles = {}
            hold_first = {u: first.get(u) for u in hold}
            for u, sol in sellers.items():
                p = hold.get(u, 0.0)
                if tw and u == tw: role = "trigger"
                elif creator and u == creator: role = "creator"
                elif p >= 6: role = "holder6"
                elif p >= 3: role = "holder3"
                elif p > 0 and first.get(u) is not None and first[u] - s0 <= 2: role = "bundle"
                elif p > 0: role = "holder<3"
                elif u in wb: role = "new_window"
                else: role = "new_hold"
                fu = first.get(u)
                clus = sum(1 for v, pv in hold.items() if v != u and pv >= 1 and hold_first.get(v) == fu) if fu is not None and p > 0 else 0
                roles[u] = {"sol": sol, "role": role, "pct_arm": p, "bot": u in botset, "cohort": u in coh, "cand": u in cand,
                            "rival": next((k for k, v in riv.items() if v == u), None), "first_rel": (fu - s0) if fu is not None else None, "cluster": clus,
                            "bundle": fu is not None and fu - s0 <= 2}
            f["sellers"] = roles
            f["buyers_in_hold"] = dict(buyers_in)
            f["sell_pre_fill"] = dict(pre)
            # live tape cross-check
            lt = collections.defaultdict(float)
            for x in w.get("tape") or []:
                if x[2] in OURS or x[3]: continue
                if (x[0], x[1]) > (fs, fi) and (x[0], x[1]) < (ss, si): lt[x[2]] += x[4] / 1e9
            f["sellers_live"] = dict(lt)
        F.append(f)
        if n % 3000 == 0: print(n, flush=True)
    pickle.dump(F, open(f"{D}/feats.pkl", "wb"))
    nf = sum(1 for w in W if w.get("filled"))
    ok = sum(1 for w, f in zip(W, F) if w.get("filled") and "sellers" in f)
    print("done", len(F), "live fills", nf, "with tape", ok)


if __name__ == "__main__":
    main()
