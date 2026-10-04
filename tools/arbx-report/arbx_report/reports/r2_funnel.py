"""R2 Funnel (MEASUREMENT.md §6.4): hints -> commit groups -> evaluations -> routes priced -> >= min_profit ->
rejections -> sent -> first verdict -> landed -> ok, with per-hour rates and status `_delta` sums as a cross-check."""
from __future__ import annotations

from . import ratio, section


def stream_down_intervals(seg) -> list:
    out = []
    down = None
    for e in sorted(seg.events, key=lambda e: e.get("t_ns") or 0):
        if e.get("kind") == "jito_stream_down" and down is None:
            down = e.get("t_ns")
        elif e.get("kind") == "jito_stream_up" and down is not None:
            out.append((down, e.get("t_ns")))
            down = None
    if down is not None:
        out.append((down, None))
    return out


def first_verdicts(seg) -> dict:
    """{attempt: category} with category in accepted, would-fail:<code>, lost-auction, processed, ..., or
    none_stream_up / none_stream_down / none_stream_unknown."""
    downs = stream_down_intervals(seg)
    sent = seg.land_rate_denominator()["sent_ids"]
    out = {}
    for a in seg.attempts:
        aid = a["attempt"]
        if aid not in sent:
            continue
        vs = seg.verdicts_by_attempt.get(aid) or []
        if vs:
            v = vs[0]
            oc = v.get("outcome")
            out[aid] = f"would-fail:{v.get('code')}" if oc == "would-fail" else oc
            continue
        if seg.legacy or not seg.events:
            out[aid] = "none_stream_unknown"
            continue
        ts = [c.get("t_sent") for c in seg.copies_by_attempt.get(aid, []) if (c.get("t_sent") or 0) > 0]
        t = min(ts) if ts else a.get("t_ns")
        in_down = any(lo <= t and (hi is None or t <= hi) for lo, hi in downs)
        out[aid] = "none_stream_down" if in_down else "none_stream_up"
    return out


def _count(it):
    d: dict = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: str(kv[0])))


def run(seg, ctx: dict) -> dict:
    sec = section("R2", "Funnel")
    d = sec["data"]
    trig = seg.jsonl("triggers")
    commits = [c for c in seg.jsonl("commits") if not c.get("late")]
    decs = seg.decisions
    routes = [r for x in decs for r in (x.get("routes") or [])]
    den = seg.land_rate_denominator()
    finals = _count(o.get("final") for o in seg.outcomes.values())
    fv = first_verdicts(seg)
    fvc = _count(fv.values())
    landed = finals.get("landed_ok", 0) + finals.get("landed_fail", 0)
    stages = [
        ["hints (decoded triggers)", len(trig) if seg.has("triggers") else None],
        ["commit groups", len(commits) if seg.has("commits") else None],
        ["evaluations (decisions)", len(decs) if seg.has("decisions") else None],
        ["routes priced", len(routes) if seg.has("decisions") else None],
        [">= min_profit (a best route)", sum(1 for x in decs if x.get("best") is not None) if seg.has("decisions") else None],
        ["attempts (signed)", len(seg.attempts)],
        ["sent (a copy with t_sent > 0 and ok)", den["sent"]],
        ["first verdict received", sum(1 for v in fv.values() if not v.startswith("none"))],
        ["landed", landed],
        ["landed ok", finals.get("landed_ok", 0)],
    ]
    d["stages"] = stages
    if seg.legacy:
        d["opportunities_v1"] = len(seg.jsonl("opportunities"))
        d["not_sent_v1 (sim-gated, counted as 'sent' by v1 status)"] = finals.get("not_sent_v1", 0)
    d["commit_outcomes"] = _count(c.get("outcome") for c in commits)
    d["trigger_skips"] = _count(t.get("skip") for t in trig if t.get("skip"))
    d["decision_verdict"] = _count(x.get("verdict") for x in decs)
    d["rejection_reasons"] = _count(x.get("reason") for x in decs if x.get("verdict") == "reject")
    d["route_reasons"] = _count(r.get("reason") for r in routes)
    d["first_verdict"] = fvc
    d["finals"] = finals
    d["land_rate"] = {"landed": landed, "sent_attempts": den["sent"], "rate": ratio(landed, den["sent"]),
                      "rule": "attempts with a copy actually sent are the denominator (§6.2 rule 4)"}
    hours = seg.window.get("trading_hours") or seg.window.get("wall_hours")
    d["per_hour"] = {"basis": "trading hours" if seg.window.get("trading_hours") else "wall hours", "hours": hours,
                     "rates": {s[0]: (round(s[1] / hours, 2) if (s[1] is not None and hours) else None) for s in stages}}
    # status cross-check: summed deltas against the streams
    agg = seg.status_agg
    if not seg.legacy and isinstance(agg, dict):
        dl = agg.get("delta", {})
        pairs = [("counts_delta.trigger", len(trig)), ("counts_delta.evaluation", len(decs)),
                 ("counts_delta.attempt", len(seg.attempts)), ("counts_delta.landed_ok", finals.get("landed_ok", 0)),
                 ("counts_delta.landed_fail", finals.get("landed_fail", 0)), ("exec.attempts_delta", len(seg.attempts))]
        d["status_cross_check"] = [{"counter": k, "status_delta_sum": dl.get(k), "streams": v,
                                    "difference": (dl.get(k) - v) if dl.get(k) is not None else None} for k, v in pairs]
        if not agg["seq"]["deltas_complete"]:
            sec["caveats"].append("status lines were lost: delta sums undercount")
    elif seg.legacy:
        st = agg if isinstance(agg, dict) else {}
        sd = st.get("sending_total") or {}
        d["status_cross_check_v1"] = {"sent_last_line": sd.get("sent"), "attempts_rows": len(seg.attempts),
                                      "landed_last_line": sd.get("landed"), "landed_outcomes": landed,
                                      "wins_last_line": sd.get("wins"), "wins_outcomes": finals.get("landed_ok", 0)}
        sec["caveats"].append("v1 'sent' counts sim-gated attempts that were never transmitted; the funnel uses copies")
    return sec
