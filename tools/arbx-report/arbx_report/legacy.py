"""arb-lab (v1) files mapped to the v2 model (MEASUREMENT.md §7).

Only fields with the same meaning are mapped; the rest are listed in `NOT_COMPARABLE` and reports print them.
Everything here is pure: it turns one v1 record into one v2-shaped dict and never reads files itself.
"""
from __future__ import annotations

#: what a v1 file cannot tell us (printed by R0 and by every report that uses the file)
NOT_COMPARABLE = {
    "status": "totals only (no deltas); profit_lamports includes rent; failed_fees_lamports misses unrecorded landings",
    "attempts": "one verdict only; nonce era; no state version, no leader telemetry; 'sent' counted sim-gated attempts",
    "outcomes": "settle-time landings only (one status check), so late landings are missing; profit includes rent",
    "copies": "kept as is",
    "exec": "PumpSwap-only (one program filter); no inner instructions, logs or keys",
    "moves": "first four columns only; no write_version",
    "poh": "entries feeds only; one clock per feed; no feed column",
    "slots-feed": "entries feeds only (v1 slots.log)",
    "alts": "final dump only; no events",
    "triggers": "decoded triggers were priced on predictions",
    "opportunities": "taker is the first tx touching both pools (misses single-pool and zero-capture closers)",
    "bundles": "no seq, no validator, no attempt",
    "meta": "feeds and send paths only; no hashes; config as Debug strings",
    "predictions": "made at hint time from the store: an earlier same-slot write makes a correct prediction look inexact",
}

V1_STAGE_KEYS = ["rx", "decoded", "engine", "resolved", "decided", "built", "signed"]


def is_v1_meta(meta: dict | None) -> bool:
    return bool(meta) and "schema" not in meta and ("strategy" in meta or "send_paths" in meta)


def attempt(a: dict) -> dict:
    """v1 attempts.jsonl line -> v2 attempt shape (unknowns are None, never 0)."""
    copies = a.get("copies") or []
    resends = a.get("bundle_resends") or []
    gross = a.get("expected_profit", a.get("predicted_profit"))
    return {
        "attempt": a.get("attempt"),
        "decision": None,
        "opp": a.get("opp"),
        "t_ns": a.get("t_ns"),
        "kind": a.get("kind"),
        "trigger": {"txn": a.get("trigger"), "slot": a.get("slot"), "kind": None, "t_first_shred": None,
                    "feed": a.get("trigger_feed")},
        "route": {"buy_pool": a.get("buy_pool"), "buy_venue": a.get("buy_venue"), "buy_source": a.get("buy_source"),
                  "sell_pool": a.get("sell_pool"), "sell_venue": a.get("sell_venue"), "sell_source": a.get("sell_source"),
                  "mint": a.get("mint"), "mint_prog": None, "hub": None},
        "size_lamports": a.get("size_lamports"),
        "expected": {"mid": a.get("predicted_mid"), "back": a.get("predicted_back"), "gross": gross,
                     "fee": a.get("worst_fee_lamports"), "tip": (copies[0].get("tip") if copies else None),
                     "net": a.get("net_at_opp")},
        "band": None,
        "min_profit_onchain": (copies[0].get("min_profit") if copies else None),
        "tx": {"sig": copies[0].get("sig") if copies else None, "cu_limit": a.get("cu_limit"),
               "cu_price_micro": a.get("cu_price_micro"), "creates_ata": a.get("creates_token_account"),
               "bytes": copies[0].get("bytes") if copies else None},
        "stages": {k: (a.get("st") or {}).get(k) for k in V1_STAGE_KEYS},
        "copies": [{"path": c.get("path"), "sig": c.get("sig"), "bytes": c.get("bytes"), "tip": c.get("tip"),
                    "min_profit": c.get("min_profit")} for c in copies]
                  + [{"path": "jito-bundle-resend", "sig": r.get("sig"), "after_ms": r.get("after_ms")} for r in resends],
        "leader": None,
        "experiments": {},
        "legacy": {"path_arm": a.get("path_arm"), "fee_arm": a.get("fee_arm"), "nonce": a.get("nonce"),
                   "not_sent": a.get("not_sent"), "priority_fee_lamports": a.get("priority_fee_lamports"),
                   "trigger_cu_price_micro": a.get("trigger_cu_price_micro"),
                   "rival_cu_price_micro": a.get("rival_cu_price_micro")},
    }


def outcome(o: dict) -> dict:
    """v1 outcomes.jsonl line -> v2 outcome shape. Finals are v1-specific where v1 could not know more:
    `landed_ok`, `landed_fail`, `not_sent_v1` (sim-gated: never transmitted), `not_landed_v1` (one status check
    after settle_s found nothing; a late landing is possible)."""
    landed_path = o.get("landed")
    se = o.get("settle_error") or ""
    if landed_path is not None:
        final = "landed_ok" if o.get("ok") else "landed_fail"
    elif "sim_gated" in se:
        final = "not_sent_v1"
    else:
        final = "not_landed_v1"
    j = o.get("jito")
    verdicts = []
    if j:
        verdicts.append({"t_ns": None, "outcome": j.get("outcome"), "slot": j.get("slot"), "validator": None,
                         "index": None, "bid": None, "code": j.get("code"), "detail": j.get("detail")})
    rt = o.get("round_trip_on_chain")
    fee, tip, profit = o.get("fee_lamports"), o.get("tip_paid_lamports"), o.get("profit_lamports")
    rent = None
    if final == "landed_ok" and None not in (rt, fee, tip, profit):
        rent = (rt - fee - tip) - profit  # lamports moved into accounts the tx created (res-pnl §2)
    return {
        "attempt": o.get("attempt"),
        "opp": o.get("opp"),
        "t_ns": o.get("t_ns"),
        "sig": o.get("sig"),
        "final": final,
        "final_src": "v1-settle",
        "amend": False,
        "verdicts": verdicts,
        "landed": ({"slot": o.get("slot"), "idx": None, "path": landed_path} if landed_path is not None else None),
        "ok": o.get("ok"),
        "err": o.get("err"),
        "code": o.get("code"),
        "meaning": o.get("meaning"),
        "fee_lamports": fee,
        "slots_after_trigger": o.get("slots_after_trigger"),
        "trigger_slot": o.get("trigger_slot"),
        "poh": o.get("poh"),
        "seen": {"by": o.get("seen_by")} if o.get("seen_by") else None,
        "send_to_seen_ms": o.get("send_to_seen_ms"),
        "delivered": o.get("delivered"),
        "predicted": o.get("predicted"),
        "round_trip_on_chain": rt,
        "round_trip_predicted": o.get("round_trip_predicted"),
        "expected_profit": o.get("expected_profit"),
        "legacy": {"tip_paid_lamports": tip, "profit_lamports": profit, "rent_residual": rent,
                   "failed_fees_lamports_running": o.get("failed_fees_lamports"), "settle_error": o.get("settle_error"),
                   "gate": o.get("gate"), "copies": o.get("copies"), "run_profit_lamports": o.get("run_profit_lamports"),
                   "cap_lamports": o.get("cap_lamports")},
    }


def bundle(b: dict) -> dict:
    out = dict(b)
    out.setdefault("seq", None)
    out.setdefault("validator", None)
    out.setdefault("attempt", None)
    return out


def status_money(line: dict) -> dict:
    """The v1 status `exec.sending` block. Every field is a running total (§4.8 v1)."""
    sd = ((line.get("exec") or {}).get("sending")) or {}
    return {k: sd.get(k) for k in ("sent", "landed", "wins", "in_flight", "failed_fees_lamports", "fees_lamports",
                                   "tips_lamports", "profit_lamports", "new_token_accounts", "cap_lamports", "stopped")}


def exec_row(e: dict) -> dict:
    """v1 exec.jsonl -> v2 field names (sol -> signer_sol, tok -> signer_tok)."""
    return {"sig": e.get("sig"), "slot": e.get("slot"), "idx": e.get("idx"), "t": e.get("t"), "ok": e.get("ok"),
            "err": e.get("err"), "why": e.get("why"), "fee": e.get("fee"), "cu": e.get("cu"), "signer": e.get("signer"),
            "signer_sol": e.get("sol"), "signer_tok": e.get("tok") or {}, "src": "grpc-tx", "venues": ["PumpSwap"],
            "legacy": True}


def research_ledger_row(r: dict) -> dict:
    """A row of the research chain ledger (work/wallet-ledger/build.py, `ledger-w5h2w5h3.jsonl`): one wallet
    signature with its chain-side money. Mapped to the fields the legacy money report needs."""
    return {"sig": r.get("sig"), "seg": r.get("seg"), "attempt": r.get("attempt"), "slot": r.get("slot"),
            "idx": r.get("tx_index"), "ok": r.get("err") is None, "fee": r.get("fee"), "tip": r.get("tip_paid") or 0,
            "wallet_sol": r.get("sol_delta"), "wsol": r.get("wsol_delta"), "rent_locked": r.get("rent_locked") or 0,
            "created": r.get("created") or [], "recorded": r.get("recorded"), "cls": r.get("cls"),
            "leader_kind": r.get("leader_kind"), "custom": r.get("custom"), "src": "research-ledger"}
