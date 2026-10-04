"""R1 Money (MEASUREMENT.md §6.4, §6.2 rules 2, 3, 10).

Money comes from the ledger (chain), never from status counters; counters are shown as a cross-check with the
difference. Rent is separate from trading. Totals carry medians and the top-1 share.

arb-lab v1 runs have no ledger. Their money is rebuilt from `outcomes.jsonl` (landings the bot recorded) plus, when
given, the wallet's chain transactions (`--wallet-txs`) or the research chain ledger (`--chain-ledger`), which add the
landings the bot never recorded (W §2, res-pnl §1).
"""
from __future__ import annotations

from .. import ledgercalc, stats
from . import LANDED_ONLY_CAVEAT, incomplete, need, section

SUMMING = ledgercalc.SUMMING


def run(seg, ctx: dict) -> dict:
    if seg.legacy:
        return run_legacy(seg, ctx)
    sec = section("R1", "Money")
    d = sec["data"]
    if not need(seg, sec, "ledger"):
        st = seg.status_agg.get("total", {}) if isinstance(seg.status_agg, dict) else {}
        d["status_counters_only"] = {k: v for k, v in st.items() if k.startswith("money.")}
        sec["caveats"].append("no ledger: the status counters above are diagnostics, not money (§6.2 rule 2)")
        return sec
    rows = seg.ledger
    cats = {c: 0 for c in SUMMING}
    info = {"rent_locked": 0, "rent_reclaimed": 0, "liquid_delta": 0}
    bad_identity = []
    eq_missing = 0
    for r in rows:
        for c in r.get("categories") or []:
            if c.get("cat") in cats:
                cats[c["cat"]] += c.get("lamports") or 0
        for k in info:
            info[k] += r.get(k) or 0
        if r.get("equity_delta") is None:
            eq_missing += 1
        v = ledgercalc.check_identities(r)
        if v:
            bad_identity.append({"sig": r.get("sig"), "violations": v})
    eq_sum = sum(r.get("equity_delta") or 0 for r in rows)
    d["ledger"] = {"transactions": len(rows), "equity_delta_sum": eq_sum, "equity_delta_missing": eq_missing,
                   "summing_categories": cats, "summing_total": sum(cats.values()), "informational": info,
                   "identity_violations": bad_identity[:50], "identity_violations_n": len(bad_identity)}
    if sum(cats.values()) != eq_sum:
        sec["caveats"].append("Σ summing categories != Σ equity_delta: the ledger is inconsistent")
    route = [r for r in rows if r.get("kind") == "route"]
    d["trading"] = {
        "trade_gross": sum(r.get("trade_gross") or 0 for r in route),
        "tips": sum(r.get("tip") or 0 for r in route if r.get("ok")),
        "fees_win": -cats["fee_win"], "fees_fail": -cats["fee_fail"], "fees_other": -cats["fee_other"],
        "trade_net": sum(r.get("trade_net") or 0 for r in route),
        "rent": {"locked": info["rent_locked"], "reclaimed": info["rent_reclaimed"],
                 "nonrecoverable": -cats["rent_nonrecoverable"]},
        "wins": sum(1 for r in route if r.get("ok")), "landed_failures": sum(1 for r in route if not r.get("ok")),
    }
    per_attempt = {}
    for r in route:
        if r.get("attempt") is not None:
            per_attempt[r["attempt"]] = per_attempt.get(r["attempt"], 0) + (r.get("trade_net") or 0)
    d["trade_net_per_attempt"] = stats.money_summary(list(per_attempt.values()))
    if d["trade_net_per_attempt"]["jackpot_flag"]:
        sec["caveats"].append("one trade is more than half of the positive total (jackpot): read the median")
    # equity from snapshots, reconciliation windows
    snaps = [s for s in seg.jsonl("snapshots") if not s.get("slot_mismatch")]
    if snaps:
        a, b = snaps[0], snaps[-1]
        d["equity"] = {"start": {k: a.get(k) for k in ("t_ns", "slot", "equity_total", "equity_liquid", "rent_recoverable")},
                       "end": {k: b.get(k) for k in ("t_ns", "slot", "equity_total", "equity_liquid", "rent_recoverable")},
                       "delta_total": (b.get("equity_total") or 0) - (a.get("equity_total") or 0),
                       "delta_liquid": (b.get("equity_liquid") or 0) - (a.get("equity_liquid") or 0)}
    else:
        incomplete(sec, "no usable snapshot: equity start/end unknown")
    rc = seg.jsonl("recon")
    d["recon"] = [{"from_slot": (r.get("from") or {}).get("slot"), "to_slot": (r.get("to") or {}).get("slot"),
                   "delta_equity": r.get("delta_equity"), "sum_entries": r.get("sum_entries"),
                   "inventory_reval": r.get("inventory_reval"), "residual": r.get("residual"),
                   "liquid_residual": (r.get("liquid") or {}).get("residual"), "ok": r.get("ok"),
                   "arithmetic": ledgercalc.recon_check(r) or "ok"} for r in rc]
    # splits by band, venue pair, leader kind, experiment arm
    d["splits"] = _splits(seg, route)
    hours = seg.window.get("trading_hours")
    d["per_hour"] = {"basis": "trading hours" if hours else "unavailable (no warm-up/gate events)",
                     "trade_net_per_hour": round(d["trading"]["trade_net"] / hours) if hours else None,
                     "hours": hours}
    _cross_checks(seg, sec, cats, route)
    _toolkit_recompute(seg, sec)
    sec["caveats"].append("rent is not trading: trade_net excludes recoverable rent (it moves liquid, not total equity)")
    return sec


def _splits(seg, route: list) -> dict:
    out: dict = {"band": {}, "venue_pair": {}, "leader_kind": {}, "experiment_arm": {}}
    for r in route:
        a = seg.attempts_by_id.get(r.get("attempt")) or {}
        rt = a.get("route") or {}
        keys = {"band": str(a.get("band")), "venue_pair": f"{rt.get('buy_venue')}>{rt.get('sell_venue')}",
                "leader_kind": str((a.get("leader") or {}).get("kind"))}
        for k, v in keys.items():
            b = out[k].setdefault(v, {"n": 0, "trade_net": 0, "wins": 0})
            b["n"] += 1
            b["trade_net"] += r.get("trade_net") or 0
            b["wins"] += bool(r.get("ok"))
        for name, arm in sorted((a.get("experiments") or {}).items()):
            b = out["experiment_arm"].setdefault(f"{name}={arm}", {"n": 0, "trade_net": 0, "wins": 0})
            b["n"] += 1
            b["trade_net"] += r.get("trade_net") or 0
            b["wins"] += bool(r.get("ok"))
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def _cross_checks(seg, sec, cats, route):
    """Status money and per-attempt outcome ledgers against the ledger (§6.2 rule 2: show the difference)."""
    d = sec["data"]
    st = seg.status_agg.get("total", {}) if isinstance(seg.status_agg, dict) else {}
    pairs = [("money.trade_net_total", sum(r.get("trade_net") or 0 for r in route)),
             ("money.tips_total", -cats["tip"]), ("money.fees_win_total", -cats["fee_win"]),
             ("money.fees_fail_total", -cats["fee_fail"]), ("money.fees_other_total", -cats["fee_other"]),
             ("money.failed_fees_total_lamports", -cats["fee_fail"])]
    cc = []
    for key, ledger_v in pairs:
        sv = st.get(key)
        cc.append({"counter": key, "status_last": sv, "ledger": ledger_v,
                   "difference": (sv - ledger_v) if sv is not None else None})
    dsum = seg.status_agg.get("delta", {}).get("money.failed_fees_delta_lamports") if isinstance(seg.status_agg, dict) else None
    cc.append({"counter": "money.failed_fees_delta_lamports (summed)", "status_last": dsum, "ledger": -cats["fee_fail"],
               "difference": (dsum - (-cats["fee_fail"])) if dsum is not None else None})
    d["status_cross_check"] = cc
    per = {"trade_net": 0, "fee": 0, "tip": 0}
    n = 0
    for o in seg.outcomes.values():
        lg = o.get("ledger")
        if lg:
            n += 1
            per["trade_net"] += lg.get("trade_net") or 0
            per["fee"] += lg.get("fee") or 0
            per["tip"] += lg.get("tip") or 0
    d["outcomes_ledger_cross_check"] = {"outcomes_with_ledger": n, "sum": per,
                                        "ledger_route": {"trade_net": sum(r.get("trade_net") or 0 for r in route),
                                                         "fee": sum(r.get("fee") or 0 for r in route),
                                                         "tip": sum(r.get("tip") or 0 for r in route)}}


def _toolkit_recompute(seg, sec):
    """Recompute every ledger line from wallet.jsonl with the toolkit's §4.42 implementation and list differences."""
    d = sec["data"]
    if not seg.has("wallet") or not seg.wallet:
        d["toolkit_recompute"] = None
        return
    diffs = []
    n = 0
    for tx in seg.wallet_txs:
        if not tx.keys:
            continue
        row = seg.ledger_by_sig.get(tx.sig)
        if row is None:
            diffs.append({"sig": tx.sig, "diff": "in wallet.jsonl but not in ledger.jsonl"})
            continue
        n += 1
        att = seg.sig_to_attempt.get(tx.sig)
        mine = ledgercalc.compute(tx, seg.wallet, route=(row.get("kind") == "route"), attempt=att,
                                  tip_accounts=ctx_tip_accounts(seg))
        for k in ("wallet_sol", "wsol", "fee", "tip", "rent_locked", "rent_reclaimed", "rent_nonrecoverable",
                  "liquid_delta", "equity_delta", "trade_gross"):
            if mine.get(k) != row.get(k):
                diffs.append({"sig": tx.sig, "field": k, "ledger": row.get(k), "toolkit": mine.get(k)})
    d["toolkit_recompute"] = {"compared": n, "differences": diffs[:50], "differences_n": len(diffs)}


def ctx_tip_accounts(seg):
    return getattr(seg, "tip_accounts", None)


# ----------------------------------------------------------------------------------------------------- legacy

def legacy_money(seg) -> dict:
    """The v1 decomposition of one segment from its outcomes (recorded) and its chain data (when given)."""
    outs = seg.outcomes
    rec = {"landed": 0, "wins": 0, "landed_failures": 0, "gross_round_trip": 0, "tips": 0, "fees_win": 0,
           "fees_fail": 0, "rent_on_wins": 0, "profit_lamports_v1": 0, "wins_without_round_trip": 0}
    win_nets = []
    by_arm: dict = {}
    landed_sigs = set()
    for a_id, o in sorted(outs.items()):
        if o["final"] not in ("landed_ok", "landed_fail"):
            continue
        rec["landed"] += 1
        landed_sigs.add(o.get("sig"))
        att = seg.attempts_by_id.get(a_id) or {}
        arm = (att.get("legacy") or {}).get("path_arm") or "unknown"
        arm = {"tpu": "direct"}.get(arm, arm)
        b = by_arm.setdefault(arm, {"landed": 0, "wins": 0, "fees_fail": 0, "trade_net": 0, "rent": 0})
        b["landed"] += 1
        lg = o.get("legacy") or {}
        fee = o.get("fee_lamports") or 0
        if o["final"] == "landed_ok":
            rec["wins"] += 1
            b["wins"] += 1
            rec["fees_win"] += fee
            rec["tips"] += lg.get("tip_paid_lamports") or 0
            rec["profit_lamports_v1"] += lg.get("profit_lamports") or 0
            rt = o.get("round_trip_on_chain")
            if rt is None:
                rec["wins_without_round_trip"] += 1
                continue
            rec["gross_round_trip"] += rt
            net = rt - fee - (lg.get("tip_paid_lamports") or 0)
            win_nets.append(net)
            b["trade_net"] += net
            rent = lg.get("rent_residual") or 0
            rec["rent_on_wins"] += rent
            b["rent"] += rent
        else:
            rec["landed_failures"] += 1
            rec["fees_fail"] += fee
            b["fees_fail"] += fee
            b["trade_net"] -= fee
            rec["profit_lamports_v1"] += 0
    rec["trade_net_recorded"] = rec["gross_round_trip"] - rec["tips"] - rec["fees_win"] - rec["fees_fail"]
    rec["profit_minus_failed_fees_v1"] = rec["profit_lamports_v1"] - rec["fees_fail"]
    out = {"recorded": rec, "by_arm": dict(sorted(by_arm.items())), "win_net": stats.money_summary(win_nets)}
    # chain side
    chain = _legacy_chain(seg, landed_sigs)
    if chain is not None:
        out["chain"] = chain
        unrec_fail = chain["unrecorded"]["fees_fail"]
        unrec_net = chain["unrecorded"]["trade_net"]
        out["trade_net_chain_corrected"] = rec["trade_net_recorded"] + unrec_net
        out["fees_fail_total"] = rec["fees_fail"] + unrec_fail
        out["landed_failures_total"] = rec["landed_failures"] + chain["unrecorded"]["landed_failures"]
        out["wins_total"] = rec["wins"] + chain["unrecorded"]["wins"]
        corr = {k: dict(v) for k, v in by_arm.items()}
        for u in chain["unrecorded"]["sigs"]:
            att = seg.attempts_by_id.get(u.get("attempt")) or {}
            arm = {"tpu": "direct"}.get((att.get("legacy") or {}).get("path_arm"), (att.get("legacy") or {}).get("path_arm") or "unknown")
            b = corr.setdefault(arm, {"landed": 0, "wins": 0, "fees_fail": 0, "trade_net": 0, "rent": 0})
            b["landed"] += 1
            if not u.get("ok"):
                b["fees_fail"] += u.get("fee") or 0
                b["trade_net"] -= u.get("fee") or 0
        out["by_arm_chain_corrected"] = dict(sorted(corr.items()))
    return out


def _legacy_chain(seg, recorded_landed: set) -> dict | None:
    """Chain-side money of this segment's signatures: wallet getTransaction results, or research ledger rows."""
    mine = seg.sig_to_attempt
    unrec = {"landed": 0, "wins": 0, "landed_failures": 0, "fees_fail": 0, "trade_net": 0, "sigs": []}
    rent = {"locked_recoverable": 0, "nonrecoverable": 0, "src": None}
    chain_tot = {"transactions": 0, "wallet_sol": 0, "wsol": 0, "fees": 0, "tips": 0}
    if seg.wallet_txs and seg.wallet:
        tips = getattr(seg, "tip_accounts", None)
        for tx in seg.wallet_txs:
            a = mine.get(tx.sig)
            if a is None:
                continue
            row = ledgercalc.compute(tx, seg.wallet, route=True, attempt=a, tip_accounts=tips)
            chain_tot["transactions"] += 1
            chain_tot["wallet_sol"] += row["wallet_sol"]
            chain_tot["wsol"] += row["wsol"]
            chain_tot["fees"] += row["fee"]
            chain_tot["tips"] += row["tip"]
            rent["locked_recoverable"] += row["rent_locked"]
            rent["nonrecoverable"] += row["rent_nonrecoverable"]
            rent["src"] = row["rent_src"]
            if tx.sig not in recorded_landed:
                unrec["landed"] += 1
                unrec["sigs"].append({"sig": tx.sig, "attempt": a, "ok": row["ok"], "fee": row["fee"]})
                if row["ok"]:
                    unrec["wins"] += 1
                    unrec["trade_net"] += row["trade_net"] or 0
                else:
                    unrec["landed_failures"] += 1
                    unrec["fees_fail"] += row["fee"]
                    unrec["trade_net"] -= row["fee"]
        src = "wallet getTransaction"
    elif seg.chain_ledger:
        for r in seg.chain_ledger:
            if r.get("seg") not in (None, seg.name):
                continue
            chain_tot["transactions"] += 1
            chain_tot["wallet_sol"] += r.get("wallet_sol") or 0
            chain_tot["wsol"] += r.get("wsol") or 0
            chain_tot["fees"] += r.get("fee") or 0
            chain_tot["tips"] += r.get("tip") or 0
            rent["locked_recoverable"] += r.get("rent_locked") or 0
            rent["src"] = "research ledger (created accounts on wins)"
            if r.get("sig") not in recorded_landed:
                unrec["landed"] += 1
                unrec["sigs"].append({"sig": r.get("sig"), "attempt": r.get("attempt"), "ok": r.get("ok"), "fee": r.get("fee")})
                if r.get("ok"):
                    unrec["wins"] += 1
                    unrec["trade_net"] += (r.get("wallet_sol") or 0) + (r.get("wsol") or 0) + (r.get("rent_locked") or 0)
                else:
                    unrec["landed_failures"] += 1
                    unrec["fees_fail"] += r.get("fee") or 0
                    unrec["trade_net"] -= r.get("fee") or 0
        src = "research chain ledger"
    else:
        return None
    unrec["sigs"].sort(key=lambda x: (x.get("attempt") is None, x.get("attempt") or 0, x.get("sig") or ""))
    chain_tot["net_wallet_change"] = chain_tot["wallet_sol"] + chain_tot["wsol"]
    return {"src": src, "totals": chain_tot, "unrecorded": unrec, "rent": rent}


def run_legacy(seg, ctx: dict) -> dict:
    sec = section("R1", "Money (arb-lab v1: outcomes + chain)")
    d = sec["data"]
    if not need(seg, sec, "outcomes"):
        return sec
    m = legacy_money(seg)
    d.update(m)
    st = seg.status_agg
    sd = (st.get("sending_total") or {}) if isinstance(st, dict) else {}
    d["status_cross_check"] = {
        "failed_fees_lamports_last_line": (st.get("failed_fees_lamports") or {}).get("last_line"),
        "failed_fees_lamports_sum_of_lines_WRONG": (st.get("failed_fees_lamports") or {}).get("sum_of_lines_WRONG"),
        "outcomes_fees_fail": m["recorded"]["fees_fail"],
        "difference_last_line": ((st.get("failed_fees_lamports") or {}).get("last_line") or 0) - m["recorded"]["fees_fail"],
        "profit_lamports_last_line": sd.get("profit_lamports"), "outcomes_profit_lamports": m["recorded"]["profit_lamports_v1"],
        "wins_last_line": sd.get("wins"), "landed_last_line": sd.get("landed"), "sent_last_line": sd.get("sent"),
    }
    sec["caveats"].append("v1 profit_lamports includes rent of accounts created by wins; trading net excludes it")
    sec["caveats"].append("v1 failed_fees_lamports is a running total: take the last line, never the sum of lines")
    if "chain" not in m:
        incomplete(sec, "no wallet chain data given (--wallet-txs or --chain-ledger): landings the bot never recorded are missing")
    sec["caveats"].append(LANDED_ONLY_CAVEAT)
    return sec


def campaign_legacy(segs: list) -> dict:
    """Sum of segment decompositions (each segment's numbers come from its own files)."""
    keys = ["landed", "wins", "landed_failures", "gross_round_trip", "tips", "fees_win", "fees_fail", "rent_on_wins",
            "profit_lamports_v1", "trade_net_recorded", "wins_without_round_trip"]
    tot = {k: 0 for k in keys}
    chain = {"landed": 0, "wins": 0, "landed_failures": 0, "fees_fail": 0, "trade_net": 0}
    have_chain = 0
    per = []
    win_nets = []
    by_arm: dict = {}
    for s in segs:
        m = legacy_money(s)
        for k in keys:
            tot[k] += m["recorded"].get(k) or 0
        for arm, b in (m.get("by_arm_chain_corrected") or m["by_arm"]).items():
            t = by_arm.setdefault(arm, {k: 0 for k in b})
            for k, v in b.items():
                t[k] += v
        row = {"segment": s.name, **{k: m["recorded"][k] for k in ("landed", "wins", "landed_failures", "fees_fail", "trade_net_recorded")}}
        if "chain" in m:
            have_chain += 1
            u = m["chain"]["unrecorded"]
            for k in chain:
                chain[k] += u[k]
            row["unrecorded_landings"] = u["landed"]
            row["unrecorded_fees_fail"] = u["fees_fail"]
            row["net_wallet_change_chain"] = m["chain"]["totals"]["net_wallet_change"]
        per.append(row)
        for o in s.outcomes.values():
            if o["final"] == "landed_ok" and o.get("round_trip_on_chain") is not None:
                win_nets.append(o["round_trip_on_chain"] - (o.get("fee_lamports") or 0) - ((o.get("legacy") or {}).get("tip_paid_lamports") or 0))
    out = {"segments": per, "recorded": tot, "by_arm": dict(sorted(by_arm.items())),
           "by_arm_basis": "chain-corrected" if have_chain == len(segs) else "recorded, chain-corrected where chain data was given",
           "win_net": stats.money_summary(win_nets)}
    if have_chain:
        out["chain_unrecorded"] = chain
        out["chain_segments"] = have_chain
        out["wins_total"] = tot["wins"] + chain["wins"]
        out["landed_failures_total"] = tot["landed_failures"] + chain["landed_failures"]
        out["fees_fail_total"] = tot["fees_fail"] + chain["fees_fail"]
        out["trade_net_chain_corrected"] = tot["trade_net_recorded"] + chain["trade_net"]
        out["net_wallet_change"] = out["trade_net_chain_corrected"] - tot["rent_on_wins"]
    return out
