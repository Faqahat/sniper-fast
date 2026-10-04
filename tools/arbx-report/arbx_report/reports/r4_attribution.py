"""R4 Attribution: who closed each gap (MEASUREMENT.md §6.4 R4, §6.2 rule 7).

Block order `(slot, idx)` and state change decide, never arrival time and never "who profited":
1. start from the decision's state version (route accounts at their `aseq`);
2. walk, in block order, every later transaction that wrote a route account (blockctx window);
3. after each one, re-price the route at the attempt's size on the post-transaction state (`arbx quote`);
4. the closer is the first transaction after which net <= the attempt's on-chain min_profit; if our transaction landed
   first and won, the closer is us; if the route never closes in the window the result is `persisted`;
5. classify the closer: `ours`, `arb_bot`, `user_swap`, `other`;
6. failed transactions cannot close a gap (they write nothing): those that touched the route are "attempted closers".
Without a pricer (WP-09) only wins (closer = ours) are attributed; the rest are listed as `needs_quote`.
"""
from __future__ import annotations

from .. import blockctx as bc
from .. import solana, stats
from ..quote import Unavailable
from . import incomplete, need, section


def classify(t: dict, known_arbers: set) -> str:
    if t.get("ours"):
        return "ours"
    pools = t.get("pools") or []
    venues = [v for v in (t.get("venues") or []) if v]
    if len(set(pools)) >= 2 or t.get("arb_like") or (t.get("signer") in known_arbers) or len(set(venues)) >= 2:
        return "arb_bot"
    if len(set(venues)) == 1 or len(set(pools)) == 1:
        return "user_swap"
    return "other"


def _start_versions(a: dict, wv_index: dict) -> dict:
    """Route accounts at the decision's version: `route_in.accounts` (acct, wv) matched to accounts.bin records.
    RPC-sourced versions have no write_version (0) and stay unresolved here; `arbx quote` resolves them."""
    out = {}
    for x in (a.get("route_in") or {}).get("accounts") or []:
        if x.get("aseq") is not None:
            out[x["acct"]] = x["aseq"]
        elif x.get("wv"):
            aseq = wv_index.get((x.get("acct"), x["wv"]))
            if aseq is not None:
                out[x["acct"]] = aseq
    return out


def attribute(seg, a: dict, row: dict, pricer, known_arbers: set, wv_index: dict | None = None) -> dict:
    o = seg.outcomes.get(a["attempt"]) or {}
    trig = row.get("trigger")
    min_profit = a.get("min_profit_onchain")
    size = a.get("size_lamports")
    ordered = []
    for s in row["slots"]:
        for t in s["txs"]:
            if t["idx"] is None:
                continue
            ordered.append((s["slot"], t["idx"], t, s))
    ordered.sort(key=lambda x: (x[0], x[1]))
    trig_tx = next((x[2] for x in ordered if x[2]["sig"] == (a.get("trigger") or {}).get("txn")), None)
    after_trigger = [x for x in ordered if trig is None or (x[0], x[1]) > (trig["slot"], trig["idx"] if trig["idx"] is not None else -1)]
    attempted = []
    versions = _start_versions(a, wv_index or {})
    res = {"attempt": a["attempt"], "result": None, "closer": None, "attempted_closers": attempted,
           "writers_after_trigger": sum(1 for x in after_trigger if x[2]["wrote"] and x[2]["ok"]),
           "complete": row["complete"]}
    pending_quote = False
    for slot, idx, t, s in after_trigger:
        if t["ours"]:
            if t["ok"]:
                res["result"] = "closed"
                res["closer"] = _closer(t, slot, idx, trig, s, "ours", trig_tx)
                return _finish(seg, a, res)
            continue
        if t["ok"] is False:  # touched the route and failed: it wrote nothing, so it cannot close the gap
            attempted.append({"sig": t["sig"], "signer": t["signer"], "slot": slot, "idx": idx,
                              "kind": classify(t, known_arbers)})
            continue
        if not t["wrote"]:
            continue
        versions.update(t.get("versions") or {})
        if pricer is None or not pricer.available():
            pending_quote = True
            continue
        try:
            net = pricer.net_after(seg, a, dict(versions), size, t["sig"])
        except Unavailable:
            pending_quote = True
            continue
        if net is None:
            res["result"] = "quote_failed"
            res["quote_failed_at"] = t["sig"]
            return _finish(seg, a, res)
        if min_profit is not None and net <= min_profit:
            res["result"] = "closed"
            res["closer"] = _closer(t, slot, idx, trig, s, classify(t, known_arbers), trig_tx)
            res["closer"]["net_after"] = net
            return _finish(seg, a, res)
    if pending_quote:
        res["result"] = "needs_quote"
    elif o.get("final") == "landed_ok":
        res["result"] = "closed"  # ours, but its position is unknown (no idx)
        res["closer"] = {"sig": o.get("sig"), "kind": "ours", "slot": (o.get("landed") or {}).get("slot"), "idx": None}
    else:
        res["result"] = "persisted" if row["complete"] else "persisted_incomplete"
    return _finish(seg, a, res)


def _closer(t, slot, idx, trig, s, kind, trig_tx: dict | None = None) -> dict:
    rel = None
    rg = None
    if trig and trig.get("idx") is not None:
        rel = {"same_slot": slot == trig["slot"], "idx_after_trigger": (idx - trig["idx"]) if slot == trig["slot"] else None,
               "slots_after_trigger": slot - trig["slot"]}
        same_bundle = bool(trig_tx and trig_tx.get("bundle_id") and trig_tx.get("bundle_id") == t.get("bundle_id"))
        rg = bc.rung((trig["slot"], trig["idx"]), (slot, idx), same_bundle)
    return {"sig": t["sig"], "signer": t["signer"], "slot": slot, "idx": idx, "kind": kind, "relative": rel,
            "rung": rg, "leader": s.get("leader"), "jito_tipped": t.get("jito_tipped"), "tip": t.get("tip")}


def _finish(seg, a, res):
    """PoH ms after the trigger (same leader's clock only) and 'seen in our feeds before our first send'."""
    c = res.get("closer")
    if not c or not c.get("sig"):
        return res
    poh = seg.__dict__.get("_poh_index") or {}
    first = seg.__dict__.get("_txarr_first") or {}
    trig = (a.get("trigger") or {}).get("txn")
    ck, tk = _s8(c["sig"]), _s8(trig) if trig else None
    pc, pt = poh.get(ck), poh.get(tk) if tk else None
    if pc and pt:
        lc = (seg.leaders.get(pc["slot"]) or {}).get("leader")
        lt = (seg.leaders.get(pt["slot"]) or {}).get("leader")
        same = pc["slot"] == pt["slot"] or (lc is not None and lc == lt)
        c["ms_after_trigger_poh"] = round(pc["ms"] - pt["ms"], 3) if same and pc["slot"] == pt["slot"] else None
        c["poh_clock"] = "same slot" if pc["slot"] == pt["slot"] else ("same leader, different slot: not compared" if same else "different leaders: not compared")
    sent = [x.get("t_sent") for x in seg.copies_by_attempt.get(a["attempt"], []) if (x.get("t_sent") or 0) > 0]
    if c["kind"] != "ours" and sent and ck in first:
        c["seen_before_our_send"] = first[ck] < min(sent)
    return res


def _s8(sig):
    try:
        return solana.sig8(sig)
    except Exception:
        return None


def run(seg, ctx: dict) -> dict:
    sec = section("R4", "Attribution: who closed each gap")
    d = sec["data"]
    if seg.legacy:
        incomplete(sec, "arb-lab v1 runs have no accounts.bin, slot index or block positions outside PumpSwap: "
                        "block-order attribution is not possible; opportunities.taker is a heuristic (W §4)")
        _legacy_taker(seg, sec)
        return sec
    ok = need(seg, sec, "accounts", "slotidx", "exec")
    built = ctx.get("blockctx") or bc.build(seg, ctx.get("chain"), ctx.get("fill_gaps", False))
    ctx["blockctx"] = built
    _index_timing(seg)
    pricer = ctx.get("pricer")
    if pricer is None or not pricer.available():
        incomplete(sec, (pricer.reason() if pricer else "no pricer") + "; only wins (closer = ours) are attributed")
    arbers = set(ctx.get("known_arbers") or [])
    for r in seg.jsonl("rivals"):
        if r.get("signer"):
            arbers.add(r["signer"])
    rows = []
    by_res: dict = {}
    by_kind: dict = {}
    for row in built["rows"]:
        a = seg.attempts_by_id[row["attempt"]]
        r = attribute(seg, a, row, pricer, arbers, built.get("wv_index"))
        row["closer"] = r.get("closer")
        rows.append(r)
        by_res[r["result"]] = by_res.get(r["result"], 0) + 1
        if r.get("closer"):
            k = r["closer"]["kind"]
            by_kind[k] = by_kind.get(k, 0) + 1
    d["attempts"] = len(rows)
    d["by_result"] = dict(sorted(by_res.items()))
    d["closer_kind"] = dict(sorted(by_kind.items()))
    rungs: dict = {}
    for r in rows:
        c = r.get("closer")
        if c and c["kind"] != "ours":
            k = bc.RUNG_NAMES.get(c.get("rung"), "unknown")
            rungs[k] = rungs.get(k, 0) + 1
    d["closer_rung"] = dict(sorted(rungs.items()))
    d["rung_note"] = "rung 0 needs bundle membership (exec.bundle); without it an idx+1 closer is rung 1"
    sig_counts: dict = {}
    for r in rows:
        c = r.get("closer")
        if c and c["kind"] != "ours" and c.get("signer"):
            sig_counts[c["signer"]] = sig_counts.get(c["signer"], 0) + 1
    d["top_closers"] = sorted(([k, v] for k, v in sig_counts.items()), key=lambda x: (-x[1], x[0]))[:20]
    rel = [r["closer"]["relative"]["idx_after_trigger"] for r in rows if r.get("closer") and r["closer"].get("relative")
           and r["closer"]["relative"].get("idx_after_trigger") is not None and r["closer"]["kind"] != "ours"]
    d["closer_idx_after_trigger"] = stats.pct(rel)
    d["attempted_closers"] = sum(len(r["attempted_closers"]) for r in rows)
    d["rows"] = rows
    d["blockctx"] = {"rows": len(built["rows"]), "complete": sum(1 for x in built["rows"] if x["complete"]),
                     "slots_processed": built["slots_processed"], "slot_refs": built["slot_refs"],
                     "gap_slots": built["gap_slots"][:100], "gaps_filled": built["gaps_filled"]}
    if not ok:
        sec["caveats"].append("block context is partial: some input streams are missing")
    return sec


def _index_timing(seg):
    if "_poh_index" not in seg.__dict__:
        from .. import streams
        idx = {}
        for p in streams.iter_poh(seg.stream_files("poh")):
            if p["sig8"] not in idx:
                idx[p["sig8"]] = p
        seg.__dict__["_poh_index"] = idx
    if "_txarr_first" not in seg.__dict__:
        from .. import streams
        seg.__dict__["_txarr_first"] = {t["sig8"]: t["first_ns"] for t in streams.iter_txarr(seg.stream_files("txarr"))}


def _legacy_taker(seg, sec):
    """What v1 recorded: opportunities.taker (the first tx touching both pools), shown with the W §4 caveat."""
    ops = seg.jsonl("opportunities")
    d = sec["data"]
    n = len(ops)
    with_taker = sum(1 for o in ops if (o.get("taker") or {}).get("sig"))
    d["v1_taker_heuristic"] = {"opportunities": n, "with_taker": with_taker,
                               "caveat": "misses single-pool and zero-capture closers (W §4); not attribution"}
