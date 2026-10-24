#!/usr/bin/env python3
"""Two-sided placement correction using block order + one-to-one arrival anchors (see arrival_bounds.py).

For each launch and L, our buy is re-placed after the last chain trade that, by evidence, arrived before L:
  + trades the model put BEHIND us but whose own arrival (wallet-only match) or a later-in-block one-to-one
    anchor is < L  (optimistic misplacement -> add)
  - matched trades the model put AHEAD of us whose arrival must be >= L because an EARLIER-in-block
    one-to-one anchor arrived at >= L (pessimistic misplacement -> drop)
Everything else as in the file (FILE hold rule).  Writes work/placement_consistency.json
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["AB_UNIQUE"] = "1"
import arrival_bounds as AB  # noqa: E402  (computes report with unique anchors)

R = AB.R
out = {}
for L in ("45", "60", "75"):
    Li = int(L)
    tot_file = 0.0
    tot_fix = 0.0
    changes = []
    fills = 0
    for x in AB.res:
        m = x["mint"]
        a = AB.rowm[m]["land"][L]
        tot_file += a["pnl"]
        info = dict(AB.L0[m][0])
        cs = info["slot"]
        tr = AB.chain[m]["trades"]
        cr = AB.chain[m]["creates"]
        info["vsol0"], info["vtok0"] = cr[0]["vsol0"], cr[0]["vtok0"]
        txs, ms_of, capped, last_ms, n_outs, _ = AB.anchors_for(m)
        pos = {t["sig"]: k for k, t in enumerate(txs)}
        cidx, glue = R.glued(tr, cs, info["idx"], info["sig"])
        floor_j = glue[-1] if glue else (cidx[-1] if cidx else -1)
        outs = R.parse_outs(AB.obs[m][0][1]["outs"])
        # model's matched set
        excl = set(cidx) | set(glue)
        ins = {info["user"], info["creator"]} | {tr[j]["user"] for j in glue}
        elig = [j for j, t in enumerate(tr) if j not in excl and t["s"] - cs < 7 and t["user"] not in ins]
        matched, _ = R.match(outs, tr, elig, Li)
        keep = []
        dropped = []
        def lo_of(jj):
            kk = pos.get(tr[jj]["sig"])
            return max([ms_of[y["sig"]] for y in txs[:kk] if y["sig"] in ms_of], default=None) if kk is not None else None
        rematched = []
        for o, j in matched:
            lo = lo_of(j)
            if lo is not None and lo >= Li:
                dropped.append(j)
                # the engine did see this wallet before L: re-match to the wallet's earliest successful trade
                # (any flag; the engine mislabels some buys as '0.000:0' sells) that is block-order consistent
                alt = [jj for jj, t in enumerate(tr) if jj not in excl and t["s"] - cs <= 6
                       and (t["user"].startswith(o["w6"]) or any(z.startswith(o["w6"]) for z in (t["signers"] or [])))
                       and (lo_of(jj) is None or lo_of(jj) < Li)]
                if alt:
                    keep.append(min(alt))
                    rematched.append((j, min(alt)))
            else:
                keep.append(j)
        # optimistic misplacements from arrival_bounds report
        rowrep = next((r for r in AB.report[L]["rows"] if r["mint"] == m), None)
        added = [z["j"] for z in rowrep["misplaced"]] if rowrep else []
        newp = max(keep + added + [floor_j])
        if newp == a["after_j"]:
            tot_fix += a["pnl"]
            fills += a["filled"]
            continue
        orig = R.match

        def forced(outs_, trades, eligible, LL, w_mode="user", mono=False, _p=newp):
            return [({"ms": 0, "sol": 0, "buy": 1, "w6": "", "n": -1}, _p)], []
        R.match = forced
        try:
            rr = R.simulate(m, info, tr, outs, Li, {"buy_slot_mode": "next"})
        finally:
            R.match = orig
        tot_fix += rr["pnl"]
        fills += rr["filled"]
        changes.append({"mint": m, "old_after_j": a["after_j"], "new_after_j": newp, "dropped_matches": dropped, "rematched": rematched,
                        "added_misplaced": added, "file_pnl": round(a["pnl"], 6), "new_pnl": round(rr["pnl"], 6),
                        "file_filled": a["filled"], "new_filled": rr["filled"], "new_ratio": round(rr["ratio"], 4)})
    out[L] = {"total_file": round(tot_file, 6), "total_block_order_consistent": round(tot_fix, 6), "fills": fills,
              "n_changed": len(changes),
              "n_optimistic_fixed": sum(1 for c in changes if c["new_after_j"] > c["old_after_j"]),
              "n_pessimistic_fixed": sum(1 for c in changes if c["new_after_j"] < c["old_after_j"]),
              "changes": changes}
json.dump(out, open(os.path.join(HERE, "work", "placement_consistency.json"), "w"), indent=1)
for L, v in out.items():
    print(L, {k: v[k] for k in v if k != "changes"})
    for c in v["changes"]:
        if c["new_after_j"] < c["old_after_j"]:
            print("    pessimistic-fix", c["mint"][:10], c["file_pnl"], "->", c["new_pnl"], c["new_filled"], c["new_ratio"])
