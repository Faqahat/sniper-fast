"""Builds report documents for a segment or a campaign from the reports' sections."""
from __future__ import annotations

import os

from . import blockctx as bc
from . import counters, ledgercalc, render, streams
from .reports import (cu_table, r0_quality, r1_money, r2_funnel, r3_attempts, r4_attribution, r5_latency, r6_leaders,
                      r7_feeds, r8_predictions, r9_rivals, r10_experiments, r11_census, r12_caps, section)

SEGMENT_ORDER = ["quality", "ledger", "funnel", "attempts", "attribution", "latency", "leaders", "feeds",
                 "predictions", "rivals", "experiments", "census", "caps", "cu-table"]

RUNNERS = {
    "quality": r0_quality.run, "ledger": r1_money.run, "money": r1_money.run, "funnel": r2_funnel.run,
    "attempts": r3_attempts.run, "attribution": r4_attribution.run, "latency": r5_latency.run,
    "leaders": r6_leaders.run, "feeds": r7_feeds.run, "predictions": r8_predictions.run, "rivals": r9_rivals.run,
    "experiments": r10_experiments.run, "census": lambda s, c: r11_census.run(s, c, "census"),
    "sizes": lambda s, c: r11_census.run(s, c, "sizes"), "sizefit": lambda s, c: r11_census.run(s, c, "sizefit"),
    "caps": r12_caps.run, "cu-table": cu_table.run,
}


def _prepare(seg, ctx: dict) -> None:
    """Block context first when its streams exist, so R0 can cite its coverage and R4/R5 can use it."""
    if not seg.legacy and seg.has("slotidx") and "blockctx" not in ctx:
        ctx["blockctx"] = bc.build(seg, ctx.get("chain"), ctx.get("fill_gaps", False))


def _inputs(seg, ctx) -> list:
    if ctx.get("quick"):
        out = []
        for stream, fis in sorted(seg.files.items()):
            for fi in fis:
                big = fi.size > 64 * 1024 * 1024
                out.append({"file": fi.name, "stream": stream, "bytes": fi.size,
                            "sha256": None if big else streams.sha256_file(fi.path), "hash_skipped": big or None})
        return out
    return seg.inputs()


def document(seg, ctx: dict, sections: list, kind: str = "segment") -> dict:
    return {"schema": "arbx.report/1.0", "tool": render.TOOL_VERSION, "kind": kind, "name": seg.name,
            "format": "v1 (arb-lab)" if seg.legacy else "v2", "window": seg.window,
            "options": {"offline": ctx.get("offline", True), "fill_gaps": bool(ctx.get("fill_gaps")),
                        "quick": bool(ctx.get("quick")),
                        "pricer": bool(ctx.get("pricer") and ctx["pricer"].available()),
                        "wallet_chain_data": bool(seg.wallet_txs) or bool(seg.chain_ledger)},
            "sections": sections, "inputs": _inputs(seg, ctx)}


def run_sections(seg, ctx: dict, names: list) -> list:
    _prepare(seg, ctx)
    out = []
    for n in names:
        sec = RUNNERS[n](seg, ctx)
        if n == "attribution":
            ctx["r4_rows"] = sec["data"].get("rows") or []
        out.append(sec)
    return out


def segment(seg, ctx: dict, names: list | None = None) -> dict:
    return document(seg, ctx, run_sections(seg, ctx, names or SEGMENT_ORDER))


def write_blockctx(seg, ctx: dict, out_dir: str) -> dict:
    _prepare(seg, ctx)
    built = ctx.get("blockctx") or bc.build(seg, ctx.get("chain"), ctx.get("fill_gaps", False))
    ctx["blockctx"] = built
    if "r4_rows" not in ctx and not seg.legacy:
        sec = r4_attribution.run(seg, ctx)
        ctx["r4_rows"] = sec["data"].get("rows") or []
    rows = bc.file_rows(built)
    render.write_jsonl(os.path.join(out_dir, "blockctx.jsonl"), rows)
    sec = section("BC", "blockctx")
    sec["data"] = {"rows": len(rows), "complete": sum(1 for r in rows if r["complete"]),
                   "slots_processed": built["slots_processed"], "slot_refs": built["slot_refs"],
                   "gap_slots": built["gap_slots"][:200], "gaps_filled": built["gaps_filled"]}
    if built["gap_slots"]:
        sec["caveats"].append("slots without a slot-index line or route writers without exec idx: rows are incomplete; "
                              "--fill-gaps with --rpc-url-env fetches those blocks")
    return sec


def ledger_rows(seg, ctx: dict) -> list:
    """The toolkit's §4.42 ledger of every wallet transaction (v2: wallet.jsonl; v1: --wallet-txs)."""
    rows = []
    for tx in seg.wallet_txs:
        att = seg.sig_to_attempt.get(tx.sig)
        if seg.legacy and att is None:
            continue
        r = ledgercalc.compute(tx, seg.wallet, route=(att is not None) if seg.legacy else None, attempt=att,
                               tip_accounts=seg.tip_accounts)
        r["identity_violations"] = ledgercalc.check_identities(r)
        rows.append(r)
    rows.sort(key=lambda r: (r.get("slot") or 0, r.get("sig") or ""))
    return rows


# --------------------------------------------------------------------------------------------------- campaign

def campaign(camp, ctx: dict) -> dict:
    segs = camp.segments
    per = []
    secs_by_seg = {}
    for s in segs:
        c2 = dict(ctx)
        c2.pop("blockctx", None)
        c2.pop("r4_rows", None)
        secs = run_sections(s, c2, ["ledger", "funnel", "attempts"])
        secs_by_seg[s.name] = secs
        r1, r2, r3 = secs
        per.append({"segment": s.name, "format": "v1" if s.legacy else "v2", "window": s.window,
                    "money": _money_line(s, r1), "attempts": dict(r2["data"]["stages"]).get("attempts (signed)"),
                    "sent": dict(r2["data"]["stages"]).get("sent (a copy with t_sent > 0 and ok)"),
                    "landed": dict(r2["data"]["stages"]).get("landed"), "landed_ok": dict(r2["data"]["stages"]).get("landed ok"),
                    "land_rate": (r3["data"].get("land_rate") or {}).get("rate")})
    out = section("C1", "Campaign")
    d = out["data"]
    d["segments"] = per
    legacy_segs = [s for s in segs if s.legacy]
    if legacy_segs:
        d["money_v1"] = r1_money.campaign_legacy(legacy_segs)
    v2 = [s for s in segs if not s.legacy]
    if v2:
        aggs = [s.status_agg for s in v2 if isinstance(s.status_agg, dict) and "total" in s.status_agg]
        keys = sorted({k for a in aggs for k in a["total"]})
        d["status_totals"] = {k: counters.campaign_total(aggs, k) for k in keys if k.startswith(("money.", "exec.", "counts_total."))}
        d["money_v2"] = _campaign_money_v2(v2)
    d["late_landings"] = _late_landings(segs)
    hours = sum((s.window.get("wall_hours") or 0) for s in segs)
    d["wall_hours"] = round(hours, 4)
    doc = {"schema": "arbx.report/1.0", "tool": render.TOOL_VERSION, "kind": "campaign", "name": camp.name,
           "campaign_json": camp.campaign_json, "sections": [out],
           "inputs": [{"segment": s.name, **i} for s in segs for i in _inputs(s, ctx)]}
    return doc


def _money_line(seg, r1) -> dict:
    d = r1["data"]
    if seg.legacy:
        rec = d.get("recorded") or {}
        return {"trade_net_recorded": rec.get("trade_net_recorded"), "trade_net_chain_corrected": d.get("trade_net_chain_corrected"),
                "wins": rec.get("wins"), "landed_failures": rec.get("landed_failures"), "fees_fail": rec.get("fees_fail"),
                "rent_on_wins": rec.get("rent_on_wins"),
                "unrecorded_landings": ((d.get("chain") or {}).get("unrecorded") or {}).get("landed")}
    t = d.get("trading") or {}
    return {k: t.get(k) for k in ("trade_net", "trade_gross", "tips", "fees_win", "fees_fail", "wins", "landed_failures")}


def _campaign_money_v2(segs) -> dict:
    cats = {c: 0 for c in ledgercalc.SUMMING}
    trade_net = 0
    for s in segs:
        for r in s.ledger:
            for c in r.get("categories") or []:
                if c.get("cat") in cats:
                    cats[c["cat"]] += c.get("lamports") or 0
            if r.get("kind") == "route":
                trade_net += r.get("trade_net") or 0
    snaps = [x for s in segs for x in s.jsonl("snapshots") if not x.get("slot_mismatch")]
    eq = None
    if snaps:
        snaps.sort(key=lambda x: (x.get("slot") or 0, x.get("t_ns") or 0))
        eq = {"start": snaps[0].get("equity_total"), "end": snaps[-1].get("equity_total"),
              "delta": (snaps[-1].get("equity_total") or 0) - (snaps[0].get("equity_total") or 0)}
    return {"summing_categories": cats, "trade_net": trade_net, "equity": eq}


def _late_landings(segs) -> list:
    """Attempts a segment left unsettled (or not landed) whose signature lands in a later segment's wallet stream."""
    out = []
    for i, s in enumerate(segs):
        open_sigs = {}
        for a in s.attempts:
            o = s.outcomes.get(a["attempt"]) or {}
            if o.get("final") in ("unsettled", "not_landed_expired", "not_landed_v1", None):
                for c in a.get("copies") or []:
                    if c.get("sig"):
                        open_sigs[c["sig"]] = a["attempt"]
        if not open_sigs:
            continue
        for later in segs[i + 1:]:
            for r in later.wallet_rows:
                if r.get("sig") in open_sigs:
                    out.append({"segment": s.name, "attempt": open_sigs[r["sig"]], "sig": r["sig"],
                                "found_in": later.name, "slot": r.get("slot"), "ok": r.get("ok")})
    return out
