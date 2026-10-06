"""cu-table (MEASUREMENT.md §6.4, §4.48; PLAN F36): per-leg compute samples from the venue programs'
`Program <id> consumed X of Y compute units` lines at the swap's invoke depth, in every watched transaction of
`exec.jsonl` (rivals included), keyed by (venue, bins-crossed bucket). Our program's overhead = our transactions' outer
consumption minus their legs. Cell limit = (overhead p99 + Σ leg p99 + ATA create/close + tip) × 1.10; a cell whose
legs have fewer than 30 samples is `fallback`. PLAN-ADDENDUM WP-21: Raydium CLMM and Orca Whirlpool legs are keyed by
the swap steps of the engine's walk (`steps_bucket`, the engine's `cu_table::steps_bucket`), known for our own
transactions (the decision's route `crossed`); a third party's leg is `unk`."""
from __future__ import annotations

import re

from .. import solana, stats
from . import incomplete, section

_INVOKE = re.compile(r"^Program (\S+) invoke \[(\d+)\]")
_CONSUMED = re.compile(r"^Program (\S+) consumed (\d+) of (\d+) compute units")
_END = re.compile(r"^Program (\S+) (success|failed)")
MIN_SAMPLES = 30
SYSTEM_TRANSFER_CU = 150
MARGIN = 1.10


def bins_bucket(n) -> str:
    if n is None:
        return "unk"
    if n == 0:
        return "0"
    if n <= 2:
        return "1-2"
    if n <= 5:
        return "3-5"
    return "6+"


def steps_bucket(n) -> str:
    """A Raydium CLMM or Orca Whirlpool leg's bucket by swap steps (src/cu_table.rs `steps_bucket`)."""
    if n is None:
        return "unk"
    if n <= 1:
        return "1"
    if n <= 3:
        return "2-3"
    if n <= 7:
        return "4-7"
    if n <= 15:
        return "8-15"
    return "16+"


def leg_key(v: str, n) -> str:
    """A leg's key in the table (src/cu_table.rs `leg_key`): DLMM by bins crossed, the CLMM venues by steps, others `na`."""
    if v == "Dlmm":
        return f"{v}|{bins_bucket(n)}"
    if v in solana.CLMM_PROGRAMS.values():
        return f"{v}|{steps_bucket(n)}"
    return f"{v}|na"


# every venue program the table samples
CU_VENUES = {**solana.VENUE_PROGRAMS, **solana.CLMM_PROGRAMS}


def parse_invocations(logs: list) -> list:
    """[(program, depth, consumed, parent_index)] in completion order, from a transaction's log lines."""
    stack = []  # [(program, depth, index in out or None)]
    out = []
    for line in logs or []:
        m = _INVOKE.match(line)
        if m:
            stack.append([m.group(1), int(m.group(2)), None])
            continue
        m = _CONSUMED.match(line)
        if m and stack and stack[-1][0] == m.group(1):
            parent = None
            for s in reversed(stack[:-1]):
                parent = s
                break
            out.append({"program": m.group(1), "depth": stack[-1][1], "consumed": int(m.group(2)),
                        "parent": parent[0] if parent else None, "seq": len(out)})
            continue
        m = _END.match(line)
        if m and stack and stack[-1][0] == m.group(1):
            stack.pop()
    return out


def run(seg, ctx: dict) -> dict:
    sec = section("CU", "cu-table")
    d = sec["data"]
    if not seg.has("exec") and not seg.has("wallet"):
        return incomplete(sec, "missing stream: exec")
    if seg.legacy:
        return incomplete(sec, "arb-lab v1 exec.jsonl has no log messages (PumpSwap results only): no CU samples")
    ours_progs = set(ctx.get("route_programs") or [])
    for p in (seg.meta or {}).get("programs") or []:
        if isinstance(p, dict) and p.get("role") == "route" and p.get("id"):
            ours_progs.add(p["id"])
    for a in seg.attempts:
        pid = (((a.get("tx") or {}).get("program")) or {}).get("id")
        if pid:
            ours_progs.add(pid)
    legs: dict = {}
    overhead = []
    ata_create, ata_close = [], []
    no_logs = 0
    seen = set()

    def ours_bins(sig):
        att = seg.sig_to_attempt.get(sig)
        a = seg.attempts_by_id.get(att) if att is not None else None
        if not a:
            return None
        dec = seg.decisions_by_id.get(a.get("decision")) or {}
        routes = dec.get("routes") or []
        b = dec.get("best")
        if b is not None and b < len(routes):
            return routes[b].get("crossed")
        return None

    sources = [seg.iter_exec()]
    if seg.has("wallet"):
        sources.append(iter(seg.wallet_rows))
    for src in sources:
        for e in src:
            sig = e.get("sig")
            if sig in seen:
                continue
            seen.add(sig)
            logs = e.get("logs")
            if logs is None:  # the provider omitted them (log_messages_none)
                no_logs += 1
                continue
            inv = parse_invocations(logs)
            crossed = ours_bins(sig)  # [buy leg, sell leg] bins crossed, in route (= invocation) order
            leg_i = 0
            leg_sum_by_parent: dict = {}
            for x in inv:
                v = CU_VENUES.get(x["program"])
                if v:
                    bc = crossed[leg_i] if (crossed and leg_i < len(crossed)) else None
                    leg_i += 1
                    key = leg_key(v, bc)
                    legs.setdefault(key, []).append(x["consumed"])
                    if x["parent"] in ours_progs:
                        leg_sum_by_parent[x["parent"]] = leg_sum_by_parent.get(x["parent"], 0) + x["consumed"]
                elif x["program"] == solana.ATA and x["depth"] == 1:
                    ata_create.append(x["consumed"])
            for x in inv:
                if x["program"] in ours_progs and x["depth"] == 1:
                    overhead.append(x["consumed"] - leg_sum_by_parent.get(x["program"], 0))
            if e.get("signer") == seg.wallet:
                for x in inv:
                    if x["program"] in solana.TOKEN_PROGRAMS and x["depth"] == 1:
                        ata_close.append(x["consumed"])
    leg_stats = {k: {"n": len(v), "p50": stats.quantile(v, 0.5), "p99": stats.quantile(v, 0.99)} for k, v in sorted(legs.items())}
    ov = {"program": sorted(ours_progs), "n": len(overhead), "p99": stats.quantile(overhead, 0.99)}
    extras = {"ata_create": stats.quantile(ata_create, 0.99) or 0, "ata_close": stats.quantile(ata_close, 0.99) or 0,
              "tip": SYSTEM_TRANSFER_CU}
    cells = {}
    pairs = set()
    for a in seg.attempts:
        rt = a.get("route") or {}
        if rt.get("buy_venue") and rt.get("sell_venue"):
            dec = seg.decisions_by_id.get(a.get("decision")) or {}
            routes = dec.get("routes") or []
            b = dec.get("best")
            cr = routes[b].get("crossed") if (b is not None and b < len(routes)) else None
            # the cell's bucket: the most bins any DLMM leg of the route crosses; WP-21: a CLMM leg's own steps bucket
            vs = (rt["buy_venue"], rt["sell_venue"])
            dl = [c for v, c in zip(vs, cr or []) if v == "Dlmm"]
            worst = max(dl) if dl else None
            steps = tuple(steps_bucket(c) if v in solana.CLMM_PROGRAMS.values() else None for v, c in zip(vs, list(cr or []) + [None, None]))
            pairs.add((rt["buy_venue"], rt["sell_venue"], bins_bucket(worst) if "Dlmm" in vs else "na",
                       bool((a.get("tx") or {}).get("creates_ata")), steps))
    for bv, sv, bb, ata, steps in sorted(pairs, key=lambda p: (p[0], p[1], p[2], p[3], tuple(x or "" for x in p[4]))):
        lk = [f"{v}|{st}" if st else f"{v}|{bb if v == 'Dlmm' else 'na'}" for v, st in zip((bv, sv), steps)]
        ns = [leg_stats.get(k, {}).get("n", 0) for k in lk]
        p99s = [leg_stats.get(k, {}).get("p99") for k in lk]
        ok = all(n >= MIN_SAMPLES for n in ns) and ov["p99"] is not None and None not in p99s
        ck = f"{bv}|{sv}|{bb}|{str(ata).lower()}" + (f"|{steps[0] or '-'}/{steps[1] or '-'}" if any(steps) else "")
        if ok:
            limit = int((ov["p99"] + sum(p99s) + (extras["ata_create"] + extras["ata_close"] if ata else 0) + extras["tip"]) * MARGIN)
            cells[ck] = {"limit": limit, "src": "legs", "leg_samples": ns}
        else:
            cells[ck] = {"limit": None, "src": "fallback", "leg_samples": ns}
    # built_ns is the segment's end (not the wall clock), so the table is reproducible from the files
    d["table"] = {"schema": "arbx.cu-table/1.0", "built_ns": seg.window.get("end_ns"), "source_runs": [seg.name],
                  "legs": leg_stats, "overhead": ov,
                  "extras": extras, "cells": cells}
    d["transactions_without_logs"] = no_logs
    if no_logs:
        sec["caveats"].append(f"{no_logs} transactions had no log messages (provider omitted them): not sampled")
    return sec
