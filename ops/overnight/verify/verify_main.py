#!/usr/bin/env python3
"""Independent verification driver for report/s4_forward.json (strategy S4).

Uses replay.py (own re-implementation from raw collector data) under two exit rules:
  FILE rule : 5-slot hold counted from the slot of the first chain trade AFTER our buy
              (this is what reproduces the file exactly)
  SPEC rule : 5-slot hold counted from our own landing slot (= slot of the trade we land after),
              i.e. the definition as written ("first trade whose slot >= our buy slot + 5")
Writes verify.json and prints a summary.  Run: python3 -I verify_main.py
"""
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replay as R  # noqa: E402

LS = ("45", "60", "75")


def r6(x):
    return None if x is None else round(x, 6)


def compare(res, rows):
    resm = {x["mint"]: x for x in res}
    out = {}
    for L in LS:
        n = len(rows)
        st = Counter()
        diffs = []
        mism = []
        tot_mine = tot_file = 0.0
        fills_mine = fills_file = 0
        for r in rows:
            a = r["land"][L]
            b = resm[r["mint"]]["land"][L]
            d = abs(a["pnl"] - b["pnl"])
            diffs.append(d)
            tot_mine += a["pnl"]
            tot_file += b["pnl"]
            fills_mine += bool(a["filled"])
            fills_file += bool(b["filled"])
            st["after_sig"] += a["after_sig"] == b["after_sig"]
            st["filled"] += a["filled"] == b["filled"]
            st["ratio4"] += abs(round(a["ratio"], 4) - b["ratio"]) <= 5e-5
            st["pnl_1e-6"] += d <= 1e-6
            st["mc_fill_2dp"] += abs(round(a["mc_fill"], 2) - b["mc_fill_sol"]) <= 0.0051
            if a["filled"] and b["filled"]:
                st["both_filled"] += 1
                st["sell_pts"] += (a.get("sell_before_sig") == b.get("sell_before_sig")
                                   and a.get("sell_after_sig") == b.get("sell_after_sig"))
                st["n_after"] += (a["buys_after"] == b["buys_after"] and a["sells_after"] == b["sells_after"])
                st["mc_sell_2dp"] += abs(round(a["mc_sell"], 2) - b["mc_sell_sol"]) <= 0.0051
            reasons = []
            if a["after_sig"] != b["after_sig"]:
                reasons.append("placement")
            if a["filled"] != b["filled"]:
                reasons.append("guard")
            if a["filled"] and b["filled"] and (a.get("sell_before_sig") != b.get("sell_before_sig")
                                                or a.get("sell_after_sig") != b.get("sell_after_sig")):
                reasons.append("exit point")
            if r["cont_breaks"]:
                reasons.append("raw data missing trade(s)")
            if d > 1e-6 or reasons and ("placement" in reasons or "guard" in reasons):
                mism.append({"mint": r["mint"], "mine_pnl": r6(a["pnl"]), "file_pnl": b["pnl"], "diff": r6(a["pnl"] - b["pnl"]),
                             "mine_filled": a["filled"], "file_filled": b["filled"], "reasons": reasons})
        out[L] = {"n": n, "matches": dict(st), "pnl_absdiff_max": r6(max(diffs)), "pnl_absdiff_mean": round(sum(diffs) / n, 8),
                  "total_mine": r6(tot_mine), "total_file": r6(tot_file), "fills_mine": fills_mine, "fills_file": fills_file,
                  "mismatches": mism}
    return out


def ahead_check(res, rows):
    resm = {x["mint"]: x for x in res}
    c = Counter()
    for r in rows:
        for L in LS:
            a = r["land"][L]
            b = resm[r["mint"]]["land"][L]
            c["ahead_eq_nonglued"] += a["ahead_nonglued"] == b["ahead"]
            c["ahead_eq_matched"] += a["matched"] == b["ahead"]
    return dict(c)


def formula_check(chain, rows):
    """Apply the replay formulas to the CHAIN pre-state of each chain trade inside the replay windows
    and compare with the on-chain token/SOL amounts."""
    db, ds = [], []
    nb = ns = 0
    for r in rows:
        tr = chain[r["mint"]]["trades"]
        end = r["cont_end_j"]
        for j in range(1, min(end + 1, len(tr))):
            t = tr[j]
            if t["is_buy"]:
                V, T = t["vsol"] - t["sol"], t["vtok"] + t["tok"]
                dT = (T * t["sol"]) // (V + t["sol"])
                db.append(dT - t["tok"])
                nb += 1
            else:
                V, T = t["vsol"] + t["sol"], t["vtok"] - t["tok"]
                dV = (V * t["tok"]) // (T + t["tok"])
                ds.append(dV - t["sol"])
                ns += 1
    return {"buys_checked": nb, "buy_tokens_diff_raw_min": min(db) if db else None, "buy_tokens_diff_raw_max": max(db) if db else None,
            "buys_exact": sum(1 for x in db if x == 0), "buys_within_2_raw": sum(1 for x in db if abs(x) <= 2),
            "sells_checked": ns, "sell_lamports_diff_min": min(ds) if ds else None, "sell_lamports_diff_max": max(ds) if ds else None,
            "sells_exact": sum(1 for x in ds if x == 0), "sells_within_2": sum(1 for x in ds if abs(x) <= 2)}


def main():
    res = json.load(open(R.RESULT))
    resm = {x["mint"]: x for x in res}
    chain = R.load_chain()
    _, rows_file = R.main({"buy_slot_mode": "next"}, write=False)
    _, rows_spec = R.main({"buy_slot_mode": "after"}, write=False)
    cmp_file = compare(res, rows_file)
    cmp_spec = compare(res, rows_spec)

    # ---- variants on matching (sensitivity) ----
    variants = {}
    for name, o in {"window_cs+5": {"match_slots": 6}, "wallet=signer": {"w_mode": "signer"},
                    "wallet=user_or_signer": {"w_mode": "either"}, "monotone_matching": {"mono": True},
                    "glue_wallets_matchable": {"excl_glue_wallets": False}, "sell_fee_at_sell": {"sell_fee_from_last": True}}.items():
        _, rv = R.main(dict(o, buy_slot_mode="next"), write=False)
        vv = {}
        for L in LS:
            ch = sum(1 for a, b in zip(rv, rows_file) if a["land"][L]["after_sig"] != b["land"][L]["after_sig"])
            vv[L] = {"placements_changed": ch, "total": r6(sum(a["land"][L]["pnl"] for a in rv)),
                     "fills": sum(1 for a in rv if a["land"][L]["filled"])}
        variants[name] = vv

    # ---- diagnostics on FILE-rule rows (they equal the file) ----
    diag = {}
    diag["ahead_field"] = ahead_check(res, rows_file)
    diag["replay_formula_vs_chain"] = formula_check(chain, rows_file)
    cont = [{"mint": r["mint"], "breaks": r["cont_breaks"]} for r in rows_file if r["cont_breaks"]]
    diag["raw_continuity_breaks"] = cont
    fee_fill = Counter()
    fee_sell = Counter()
    vfill = []
    for r in rows_file:
        tr = chain[r["mint"]]["trades"]
        pos = {t["sig"]: j for j, t in enumerate(tr)}
        for L in LS:
            a = r["land"][L]
            if not a["filled"]:
                continue
            fee_fill[a["fee_bps_total"]] += 1
            sa = pos.get(a["sell_after_sig"])
            if sa is not None:
                t = tr[sa]
                fee_sell[t["fee_bps"] + t["cfee_bps"]] += 1
            vfill.append(a["V_fill"] / 1e9)
    diag["fee_bps_total_at_fill"] = dict(fee_fill)
    diag["fee_bps_total_at_sell_point_chain"] = dict(fee_sell)
    diag["vsol_at_fill_range"] = [round(min(vfill), 3), round(max(vfill), 3)] if vfill else None

    # concentration / graduation / hold length / placement depth
    conc = {}
    for tag, rows in (("file_rule", rows_file), ("spec_rule", rows_spec)):
        cc = {}
        for L in LS:
            p = sorted([(r["land"][L]["pnl"], r["mint"]) for r in rows if r["land"][L]["filled"]], reverse=True)
            tot = sum(r["land"][L]["pnl"] for r in rows)
            top5 = sum(x for x, _ in p[:5])
            top1 = p[0][0] if p else 0
            pos_sum = sum(x for x, _ in p if x > 0)
            wins = sum(1 for x, _ in p if x > 0)
            cc[L] = {"total": r6(tot), "fills": len(p), "wins": wins, "losses": len(p) - wins,
                     "fails": sum(1 for r in rows if not r["land"][L]["filled"]),
                     "fail_cost": r6(sum(r["land"][L]["pnl"] for r in rows if not r["land"][L]["filled"])),
                     "top1": r6(top1), "top5_sum": r6(top5), "top5_share_of_total": round(top5 / tot, 3) if tot else None,
                     "top5_share_of_gross_wins": round(top5 / pos_sum, 3) if pos_sum else None,
                     "total_ex_top5": r6(tot - top5), "total_ex_top1": r6(tot - top1),
                     "top5": [(m, r6(x)) for x, m in p[:5]], "worst3": [(m, r6(x)) for x, m in p[-3:]],
                     "median_fill_pnl": r6(p[len(p) // 2][0]) if p else None}
            g = [(r["mint"], r6(r["land"][L]["pnl"])) for r in rows if r["land"][L]["filled"] and r["land"][L].get("grad")]
            cc[L]["graduation_sells"] = g
            cc[L]["graduation_pnl"] = r6(sum(x for _, x in g))
            nl = [(r["mint"], r6(r["land"][L]["pnl"])) for r in rows if r["land"][L]["filled"] and r["land"][L].get("no_later_trade")]
            cc[L]["sold_at_final_state_no_later_trade"] = nl
        conc[tag] = cc
    diag["concentration"] = conc

    hold = {}
    for L in LS:
        hs = []
        big = []
        for r in rows_file:
            a = r["land"][L]
            if not a["filled"]:
                continue
            ss = a.get("sell_slot")
            # slots between our landing slot and the trade we sell in front of (None = sold at final state)
            tr = chain[r["mint"]]["trades"]
            pos = {t["sig"]: j for j, t in enumerate(tr)}
            last_rep = tr[pos[a["sell_after_sig"]]]["s"] - a["buy_slot_landing"] if a.get("sell_after_sig") in pos else None
            hs.append(last_rep)
            if last_rep is not None and last_rep > 5:
                big.append((r["mint"], last_rep))
        hold[L] = {"fills": len(hs), "last_replayed_trade_slot_offset_gt5": len(big),
                   "max_offset": max([h for h in hs if h is not None], default=None),
                   "examples": sorted(big, key=lambda x: -x[1])[:8]}
    diag["file_rule_hold_length"] = hold

    depth = {}
    for L in LS:
        c = Counter()
        for r in rows_file:
            a = r["land"][L]
            if a["filled"]:
                c[a["buy_slot_landing"] - r["create_event"]["slot"]] += 1
        depth[L] = dict(sorted(c.items()))
    diag["fill_landing_slot_offset_from_create"] = depth

    # mayhem / quote / curve sanity
    cur = Counter()
    odd = []
    for r in rows_file:
        ce = r.get("create_event") or {}
        key = (ce.get("vsol0"), ce.get("vtok0"), ce.get("rtok0"), ce.get("supply"), ce.get("token_program"),
               (ce.get("tail_hex") or "")[:2])
        cur[str(key)] += 1
        vf = [r["land"][L]["V_fill"] / 1e9 for L in LS]
        if ce.get("vsol0") != 30_000_000_000 or min(vf) < 25 or max(vf) > 200 or (ce.get("tail_hex") or "00")[:2] != "00":
            odd.append({"mint": r["mint"], "vsol0": ce.get("vsol0"), "tail": (ce.get("tail_hex") or "")[:8], "vfill": vf})
    diag["curve_params"] = dict(cur)
    diag["curve_anomalies"] = odd

    # unmatched outs before L in FILLED rows: could a real trade ahead of us have been missed?
    obs = R.load_obs({r["mint"] for r in rows_file})
    miss = Counter()
    miss_ex = []
    for r in rows_file:
        tr = chain[r["mint"]]["trades"]
        cs = r["create_event"]["slot"]
        outs = R.parse_outs(obs[r["mint"]][0][1]["outs"])
        for L in LS:
            a = r["land"][L]
            if not a["filled"]:
                continue
            for o in outs:
                if o["ms"] >= int(L):
                    continue
                # does this wallet have a chain trade in the window AFTER our position (would push us later)?
                later = [j for j, t in enumerate(tr) if j > a["after_j"] and t["s"] - cs <= 6
                         and (t["user"].startswith(o["w6"]) or any(s.startswith(o["w6"]) for s in (t["signers"] or [])))
                         and bool(t["is_buy"]) == bool(o["buy"])]
                if later:
                    miss[L] += 1
                    if len(miss_ex) < 12:
                        t = tr[later[0]]
                        miss_ex.append({"mint": r["mint"], "L": L, "out": o, "chain_sol": t["sol"] / 1e9, "chain_slot_off": t["s"] - cs})
    diag["outs_before_L_with_same_wallet_trade_after_us"] = {"counts": dict(miss), "examples": miss_ex}

    per = []
    for rf, rs in zip(rows_file, rows_spec):
        b = resm[rf["mint"]]
        e = {"mint": rf["mint"], "name": b.get("name"), "bt": b["bt"], "land": {}}
        for L in LS:
            a, s_ = rf["land"][L], rs["land"][L]
            e["land"][L] = {"after_sig": a["after_sig"], "after_sig_match": a["after_sig"] == b["land"][L]["after_sig"],
                            "ratio": round(a["ratio"], 6), "filled": a["filled"], "filled_match": a["filled"] == b["land"][L]["filled"],
                            "pnl_mine_file_rule": r6(a["pnl"]), "pnl_file": b["land"][L]["pnl"],
                            "pnl_diff": r6(a["pnl"] - b["land"][L]["pnl"]), "pnl_mine_spec_rule": r6(s_["pnl"]),
                            "fee_bps_total": a.get("fee_bps_total"), "X": a.get("X"), "q": a.get("q"), "q_eff": a.get("q_eff"),
                            "V_fill": a["V_fill"], "T_fill": a["T_fill"], "V_sell": a.get("V_sell"), "T_sell": a.get("T_sell"),
                            "sell_after_sig": a.get("sell_after_sig"), "sell_before_sig": a.get("sell_before_sig"),
                            "spec_sell_before_sig": s_.get("sell_before_sig"), "grad": a.get("grad")}
        e["raw_continuity_breaks"] = rf["cont_breaks"]
        per.append(e)

    summary = {"file_rule_vs_file": cmp_file, "spec_rule_vs_file": cmp_spec, "matching_variants_file_rule": variants,
               "diagnostics": diag}
    with open(os.path.join(HERE, "verify.json"), "w") as fh:
        json.dump({"summary": summary, "per_launch": per}, fh, indent=1, default=str)

    for tag, cm in (("FILE-rule (reproduction)", cmp_file), ("SPEC-rule (definition as written)", cmp_spec)):
        print("==", tag)
        for L in LS:
            c = cm[L]
            print(f"  L{L}: matches {c['matches']} | pnl |d| max {c['pnl_absdiff_max']} mean {c['pnl_absdiff_mean']} | "
                  f"fills mine {c['fills_mine']} file {c['fills_file']} | total mine {c['total_mine']} file {c['total_file']} | mism {len(c['mismatches'])}")
    print("variants", json.dumps(variants))
    print("diag", json.dumps({k: v for k, v in diag.items() if k not in ("concentration",)}, default=str)[:6000])
    print("conc", json.dumps(conc, default=str)[:6000])


if __name__ == "__main__":
    main()
