#!/usr/bin/env python3
"""Placement realism check (skeptic task 3a, extended).

The model puts our buy right after the last chain trade that the engine saw before L ms.
Here every outside tx in block order (successful AND failed, slots cs..cs+6) is anchored to the
engine's arrival times (outs) by signer prefix, so the arrival time of each successful trade that the
model places BEHIND us can be bounded:
  own_ms>=L / lower_bound>=L  -> legit (arrived after our landing time)
  own_ms<L  / upper_bound<L   -> MISPLACED (arrived before L, should be ahead of us)  [optimistic]
  otherwise                   -> ambiguous
Monotonicity of arrival vs block order is measured first.  Writes work/arrival_bounds.json
"""
import gzip
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replay as R  # noqa: E402

res = json.load(open(R.RESULT))
mints = {x["mint"] for x in res}
chain = R.load_chain()
obs = R.load_obs(mints)
L0 = R.load_launches(mints)
allx = json.load(gzip.open(os.path.join(HERE, "work", "alltx_early.json.gz"), "rt"))
bym = defaultdict(list)
for x in allx:
    bym[x["mint"]].append(x)
_, rows = R.main({"buy_slot_mode": "next"}, write=False)
UNIQUE = os.environ.get("AB_UNIQUE", "1") == "1"   # default: one-to-one anchors only (robust)
rowm = {r["mint"]: r for r in rows}


def anchors_for(m):
    info = L0[m][0]
    cs = info["slot"]
    tr = chain[m]["trades"]
    cidx, glue = R.glued(tr, cs, info["idx"], info["sig"])
    glue_sigs = {tr[j]["sig"] for j in glue} | {info["sig"]}
    insiders = {info["user"], info["creator"]}
    txs = [x for x in bym[m] if x["s"] - cs <= 6 and x["sig"] not in glue_sigs
           and not (set(x["signers"] or []) & insiders)]
    txs.sort(key=lambda x: (x["s"], x["i"]))
    outs = R.parse_outs(obs[m][0][1]["outs"])
    outs_sorted = sorted(outs, key=lambda o: (o["ms"], o["n"]))
    used = set()
    ms_of = {}
    if UNIQUE:
        # only one-to-one anchors: wallet prefix appears exactly once in outs and once among window txs
        cnt_o = Counter(o["w6"] for o in outs)
        for o in outs_sorted:
            if cnt_o[o["w6"]] != 1:
                continue
            hits = [x for x in txs if any(s.startswith(o["w6"]) for s in (x["signers"] or []))]
            if len(hits) == 1:
                ms_of[hits[0]["sig"]] = o["ms"]
    else:
        for o in outs_sorted:
            for k, x in enumerate(txs):
                if k in used:
                    continue
                if any(s.startswith(o["w6"]) for s in (x["signers"] or [])):
                    used.add(k)
                    ms_of[x["sig"]] = o["ms"]
                    break
    capped = len(outs) >= 24
    last_ms = max([o["ms"] for o in outs], default=None)
    return txs, ms_of, capped, last_ms, len(outs), sum(1 for o in outs if True) - len(ms_of)


# --- monotonicity: anchored txs in block order should have non-decreasing ms ---
inv = 0
pairs = 0
inv_big = 0
inv_slot = 0
for m in mints:
    txs, ms_of, *_ = anchors_for(m)
    seq = [(ms_of[x["sig"]], x["s"]) for x in txs if x["sig"] in ms_of]
    for (a, sa), (b, sb) in zip(seq, seq[1:]):
        pairs += 1
        if b < a:
            inv += 1
            if a - b > 5:
                inv_big += 1
                if sb > sa:
                    inv_slot += 1
mono = {"adjacent_pairs": pairs, "inversions": inv, "inversions_gt5ms": inv_big, "inversions_gt5ms_across_slot_boundary": inv_slot}

report = {"monotonicity": mono}
for L in ("45", "60", "75"):
    Li = int(L)
    cat = Counter()
    solcat = Counter()
    rows_out = []
    for x in res:
        m = x["mint"]
        a = rowm[m]["land"][L]
        if not a["filled"]:
            continue
        info = L0[m][0]
        cs = info["slot"]
        tr = chain[m]["trades"]
        txs, ms_of, capped, last_ms, n_outs, _ = anchors_for(m)
        pos = {t["sig"]: k for k, t in enumerate(txs)}
        our_sig = a["after_sig"]
        # block position of our landing point
        after_t = tr[a["after_j"]]
        our_key = (after_t["s"], after_t["i"])
        bad = []
        amb = []
        for j in range(a["after_j"] + 1, len(tr)):
            t = tr[j]
            if t["s"] - cs > 6:
                break
            if t["user"] in (info["user"], info["creator"]):
                cat["insider"] += 1
                continue
            if (t["s"], t["i"]) == our_key:
                continue  # same tx as our anchor (multi-event tx)
            k = pos.get(t["sig"])
            own = ms_of.get(t["sig"])
            lo = max([ms_of[y["sig"]] for y in txs[:k] if y["sig"] in ms_of], default=None) if k is not None else None
            hi = min([ms_of[y["sig"]] for y in txs[k + 1:] if y["sig"] in ms_of], default=None) if k is not None else None
            if own is not None:
                c = "own_ms>=L" if own >= Li else "own_ms<L MISPLACED"
            elif hi is not None and hi < Li:
                c = "upper<L MISPLACED"
            elif lo is not None and lo >= Li:
                c = "lower>=L"
            elif capped and k is not None and lo is not None and all(y["sig"] not in ms_of for y in txs[k + 1:]) and last_ms >= Li:
                c = "after_cap>=L"
            else:
                c = "ambiguous"
            cat[c] += 1
            if t["is_buy"]:
                solcat[c] += t["sol"] / 1e9
            if "MISPLACED" in c:
                bad.append({"j": j, "slot_off": t["s"] - cs, "i": t["i"], "is_buy": t["is_buy"], "sol": round(t["sol"] / 1e9, 4),
                            "user": t["user"][:8], "own_ms": own, "upper_ms": hi})
            elif c == "ambiguous":
                amb.append({"j": j, "slot_off": t["s"] - cs, "i": t["i"], "is_buy": t["is_buy"], "sol": round(t["sol"] / 1e9, 4),
                            "lo": lo, "hi": hi})
        rows_out.append({"mint": m, "pnl": a["pnl"], "misplaced": bad, "ambiguous": amb})
    report[L] = {"categories": dict(cat), "buy_sol": {k: round(v, 2) for k, v in solcat.items()},
                 "fills": len(rows_out), "fills_with_misplaced": sum(1 for r in rows_out if r["misplaced"]),
                 "fills_with_ambiguous_buys": sum(1 for r in rows_out if any(z["is_buy"] for z in r["ambiguous"])),
                 "rows": rows_out}


# --- re-simulate: put our buy after the last MISPLACED trade (what the model's own rule implies) ---
def resim(m, L, new_j):
    tr = chain[m]["trades"]
    info = dict(L0[m][0])
    cr = chain[m]["creates"]
    info["vsol0"], info["vtok0"] = cr[0]["vsol0"], cr[0]["vtok0"]
    orig = R.match

    def forced(outs, trades, eligible, LL, w_mode="user", mono=False):
        mm, um = orig(outs, trades, eligible, LL, w_mode, mono)
        return mm + [({"ms": 0, "sol": 0, "buy": 1, "w6": "", "n": -1}, new_j)], um
    R.match = forced
    try:
        rr = R.simulate(m, info, tr, R.parse_outs(obs[m][0][1]["outs"]), int(L), {"buy_slot_mode": "next"})
    finally:
        R.match = orig
    return rr


for L in ("45", "60", "75"):
    delta = 0.0
    fl = 0
    for r in report[L]["rows"]:
        if r["misplaced"]:
            nj = max(z["j"] for z in r["misplaced"])
            rr = resim(r["mint"], L, nj)
            r["fixed"] = {"pnl": round(rr["pnl"], 6), "filled": rr["filled"], "ratio": round(rr["ratio"], 4)}
            delta += rr["pnl"] - r["pnl"]
            fl += (not rr["filled"])
    tot_file = sum(rowm[m]["land"][L]["pnl"] for m in mints)
    report[L]["pnl_delta_if_misplaced_fixed"] = round(delta, 6)
    report[L]["fills_lost_if_fixed"] = fl
    report[L]["total_file"] = round(tot_file, 6)
    report[L]["total_if_fixed"] = round(tot_file + delta, 6)
    amb_pnl = sum(r["pnl"] for r in report[L]["rows"] if any(z["is_buy"] for z in r["ambiguous"]) and not r["misplaced"])
    report[L]["pnl_of_fills_with_only_ambiguous_buys_behind"] = round(amb_pnl, 6)

report["anchor_mode"] = "unique" if UNIQUE else "greedy"
json.dump(report, open(os.path.join(HERE, "work", "arrival_bounds_%s.json" % report["anchor_mode"]), "w"), indent=1)
print("monotonicity", mono)
for L in ("45", "60", "75"):
    v = report[L]
    print(L, {k: v[k] for k in v if k != "rows"})
    for r in v["rows"]:
        if r["misplaced"]:
            print("   MIS", r["mint"][:10], "pnl", round(r["pnl"], 4), "->", r.get("fixed"), r["misplaced"][:3])
