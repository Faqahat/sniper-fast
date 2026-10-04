"""R6 Leaders (MEASUREMENT.md §6.4): slot share by kind; attempts, accepted and landed by kind, region, client,
host->leader RTT bucket and block-engine RTT bucket; landings per 1,000 eligible slots by kind (X5) with CIs."""
from __future__ import annotations

from .. import stats
from . import incomplete, need, ratio, section
from .r3_attempts import rtt_bucket


def run(seg, ctx: dict) -> dict:
    sec = section("R6", "Leaders")
    d = sec["data"]
    if seg.legacy:
        return incomplete(sec, "arb-lab v1 recorded no leader telemetry (BAM status came from a static file)")
    if not need(seg, sec, "leaders"):
        return sec
    kinds: dict = {}
    for r in seg.leaders.values():
        kinds[r.get("kind") or "unknown"] = kinds.get(r.get("kind") or "unknown", 0) + 1
    tot = sum(kinds.values())
    d["slot_share"] = {k: {"slots": v, "share": ratio(v, tot)} for k, v in sorted(kinds.items())}
    dims: dict = {}
    for a in seg.attempts:
        ld = a.get("leader") or {}
        vs = seg.verdicts_by_attempt.get(a["attempt"]) or []
        o = seg.outcomes.get(a["attempt"]) or {}
        acc = any(v.get("outcome") == "accepted" for v in vs)
        landed = o.get("final") in ("landed_ok", "landed_fail")
        for dim, val in (("kind", ld.get("kind")), ("region", ld.get("region")), ("client", ld.get("client")),
                         ("host_leader_rtt", rtt_bucket(ld.get("rtt_ms"))), ("block_engine_rtt", rtt_bucket(ld.get("be_rtt_ms")))):
            b = dims.setdefault(dim, {}).setdefault(str(val), {"attempts": 0, "accepted": 0, "landed": 0})
            b["attempts"] += 1
            b["accepted"] += acc
            b["landed"] += landed
    for dim in dims.values():
        for b in dim.values():
            b["land_rate"] = ratio(b["landed"], b["attempts"])
            b["ci95"] = stats.wilson(b["landed"], b["attempts"])
    d["by"] = {k: dict(sorted(v.items())) for k, v in sorted(dims.items())}
    per1000 = {}
    for k, slots in kinds.items():
        landed = (dims.get("kind", {}).get(k) or {}).get("landed", 0)
        per1000[k] = {"eligible_slots": slots, "landed": landed, "per_1000_slots": round(1000 * landed / slots, 3) if slots else None,
                      "ci95_per_1000": [round(1000 * x, 3) for x in (stats.wilson(landed, slots) or [0, 0])] if slots else None}
    d["landings_per_1000_slots"] = dict(sorted(per1000.items()))
    sec["caveats"].append("host -> leader RTT is our QUIC handshake to the leader's TPU, not the bundle's path "
                          "(block engine -> leader); the block-engine RTT is be_rtt_ms")
    return sec
