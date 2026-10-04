"""R5 Latency (MEASUREMENT.md §6.4): stage decomposition (A.8 names, microseconds), commit lag, the state-lag SLO per
minute, and ours against closers in PoH ms after the trigger. Wall-clock differences are on one host clock."""
from __future__ import annotations

from .. import stats
from . import section

V2_CHAIN = ["t_first_shred", "t_update_recv", "t_commit", "t_engine", "t_priced", "t_decided", "t_built", "t_signed",
            "t_enqueued", "t_sent", "t_ack"]
V1_CHAIN = ["rx", "decoded", "engine", "resolved", "decided", "built", "signed"]


def _name(a, b):
    return f"{a.removeprefix('t_')}→{b.removeprefix('t_')}"


def _pairs(rows: list, chain: list) -> dict:
    out: dict = {}
    for st in rows:
        for a, b in zip(chain, chain[1:]):
            x, y = st.get(a), st.get(b)
            if x is None or y is None:
                continue
            out.setdefault(_name(a, b), []).append((y - x) / 1000.0)
    return {k: stats.pct(v) for k, v in out.items()}


def run(seg, ctx: dict) -> dict:
    sec = section("R5", "Latency")
    d = sec["data"]
    d["unit"] = "microseconds"
    if seg.legacy:
        rows = []
        for a in seg.attempts:
            st = dict(a.get("stages") or {})
            ts = [c.get("t_sent") for c in seg.copies_by_attempt.get(a["attempt"], []) if (c.get("t_sent") or 0) > 0]
            acks = [c.get("t_ack") for c in seg.copies_by_attempt.get(a["attempt"], []) if (c.get("t_ack") or 0) > 0]
            st["sent"] = min(ts) if ts else None
            st["ack"] = min(acks) if acks else None
            rows.append(st)
        d["attempt_stages_v1"] = _pairs(rows, V1_CHAIN + ["sent", "ack"])
        sts = [o.get("send_to_seen_ms") for o in seg.outcomes.values() if o.get("send_to_seen_ms") is not None]
        d["sent→seen_ms"] = stats.pct(sts)
        last = seg.status[-1] if seg.status else {}
        d["status_latency_v1_last_line"] = last.get("latency")
        sec["caveats"].append("v1 stages: state-trigger attempts filled every stage with one time before WP-00 (F13)")
        return sec
    att_st = []
    extra: dict = {"sent→first_verdict": [], "sent→seen": [], "sent→landed(wallet fetch)": []}
    for a in seg.attempts:
        st = a.get("stages") or {}
        att_st.append(st)
        t_sent = st.get("t_sent")
        if t_sent is None:
            continue
        vs = seg.verdicts_by_attempt.get(a["attempt"]) or []
        if vs and vs[0].get("t_ns"):
            extra["sent→first_verdict"].append((vs[0]["t_ns"] - t_sent) / 1000.0)
        o = seg.outcomes.get(a["attempt"]) or {}
        fs = (o.get("seen") or {}).get("first_ns")
        if fs:
            extra["sent→seen"].append((fs - t_sent) / 1000.0)
        tw = (o.get("landed") or {}).get("t_wallet_ns")
        if tw:
            extra["sent→landed(wallet fetch)"].append((tw - t_sent) / 1000.0)
    d["attempt_stages"] = _pairs(att_st, V2_CHAIN)
    d["attempt_stages"].update({k: stats.pct(v) for k, v in extra.items()})
    d["decision_stages"] = _pairs([x.get("stages") or {} for x in seg.decisions], V2_CHAIN[:6])
    cm = [c for c in seg.jsonl("commits") if not c.get("late")]
    d["commit_lag_ms"] = {"all": stats.pct([c["lag_ms"] for c in cm if c.get("lag_ms") is not None])}
    for src in sorted({c.get("w_src") for c in cm}, key=str):
        d["commit_lag_ms"][str(src)] = stats.pct([c["lag_ms"] for c in cm if c.get("w_src") == src and c.get("lag_ms") is not None])
    slo = [s.get("lag_slo") for s in seg.status if s.get("lag_slo")]
    d["lag_slo_minutes"] = {"lines": len(slo), "breaches": sum(1 for x in slo if x.get("ok") is False),
                            "p90_ms_by_line": stats.pct([x.get("p90_ms") for x in slo if x.get("p90_ms") is not None])}
    r4 = ctx.get("r4_rows") or []
    closers = [r["closer"].get("ms_after_trigger_poh") for r in r4 if r.get("closer") and r["closer"]["kind"] != "ours"
               and r["closer"].get("ms_after_trigger_poh") is not None]
    ours = [((o.get("poh") or {}).get("ours_ms_after_trigger")) for o in seg.outcomes.values()]
    d["poh_ms_after_trigger"] = {"ours": stats.pct([x for x in ours if x is not None]), "closers": stats.pct(closers),
                                 "note": "PoH ms compared only on the same leader's clock (same slot)"}
    return sec
