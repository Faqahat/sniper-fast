"""Counter semantics of every periodic stream (MEASUREMENT.md §2.2, §6.2 rule 1).

- `<name>_total` is monotonic since process start: a segment's value is the LAST line's; never sum it.
- `<name>_delta` is the change since the previous line: the segment's value is the SUM over lines.
- `<name>_now` is a gauge: report last and max, never sum.
- The rule applies to a key and to everything under it (`counts_total: {name: n}`, `verdicts_delta: {outcome: n}`).
- A `seq` gap means lost lines: the deltas of the lost lines are missing, so delta sums are flagged incomplete.
arb-lab's `failed_fees_lamports` was a running total that its supervisor summed across lines (R §3.7).
"""
from __future__ import annotations


def _special(name: str) -> str | None:
    # the suffix decides (`equity_total_now` is a gauge); a unit after it is allowed (`failed_fees_total_lamports`)
    for suf, kind in (("_now", "now"), ("_total", "total"), ("_delta", "delta")):
        if name.endswith(suf):
            return kind
    for suf, kind in (("_total_", "total"), ("_delta_", "delta"), ("_now_", "now")):
        if suf in name:
            return kind
    return None


def _walk(obj, path, kind, out):
    if isinstance(obj, dict):
        if "window" in obj and "n" in obj and ("p50" in obj or "p50_ms" in obj):
            return  # a percentile object: windows cannot be merged
        for k, v in obj.items():
            kk = _special(k) or kind
            _walk(v, path + (k,), kk, out)
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        if kind is not None:
            out.append((path, kind, obj))


def aggregate(lines: list) -> dict:
    """{"total": {path: last}, "delta": {path: sum}, "now": {path: {last, max}}, "seq": {...}} for one segment."""
    totals: dict = {}
    deltas: dict = {}
    gauges: dict = {}
    for ln in lines:
        flat: list = []
        _walk({k: v for k, v in ln.items() if k not in ("seq", "t_ns", "interval_ns")}, (), None, flat)
        for path, kind, v in flat:
            key = ".".join(path)
            if kind == "total":
                totals[key] = v
            elif kind == "delta":
                deltas[key] = deltas.get(key, 0) + v
            elif kind == "now":
                g = gauges.setdefault(key, {"last": v, "max": v})
                g["last"] = v
                g["max"] = max(g["max"], v)
    return {"total": dict(sorted(totals.items())), "delta": dict(sorted(deltas.items())),
            "now": dict(sorted(gauges.items())), "seq": seq_check(lines)}


def seq_check(lines: list) -> dict:
    seqs = [ln.get("seq") for ln in lines if isinstance(ln.get("seq"), int)]
    gaps = []
    restarts = 0
    for a, b in zip(seqs, seqs[1:]):
        if b == 0:
            restarts += 1  # a new process wrote into the same file
        elif b != a + 1:
            gaps.append([a + 1, b - 1])
    return {"lines": len(lines), "with_seq": len(seqs), "first": seqs[0] if seqs else None,
            "last": seqs[-1] if seqs else None, "gaps": gaps, "lost_lines": sum(g[1] - g[0] + 1 for g in gaps if g[1] >= g[0]),
            "restarts": restarts, "deltas_complete": not gaps and len(seqs) == len(lines) and (not seqs or seqs[0] == 0)}


def campaign_total(segment_aggs: list, key: str):
    """Across segments: the sum of each segment's last `_total` (each segment is one process)."""
    vals = [a["total"].get(key) for a in segment_aggs]
    have = [v for v in vals if v is not None]
    return {"value": sum(have) if have else None, "segments": len(vals), "missing": len(vals) - len(have)}


def legacy_status(lines: list) -> dict:
    """arb-lab v1 status.jsonl: every number is a running total. The segment value is the last line; the sum over
    lines (arb-lab's supervisor mistake) is shown beside it so the error is visible."""
    if not lines:
        return {"lines": 0}
    last = lines[-1]
    sd = ((last.get("exec") or {}).get("sending")) or {}
    summed = sum((((ln.get("exec") or {}).get("sending")) or {}).get("failed_fees_lamports") or 0 for ln in lines)
    return {"lines": len(lines), "t_ns_last": last.get("t_ns"), "counts_total": dict(sorted((last.get("counts") or {}).items())),
            "exec_counts_total": dict(sorted(((last.get("exec") or {}).get("counts") or {}).items())),
            "sending_total": {k: sd.get(k) for k in sorted(sd)},
            "failed_fees_lamports": {"last_line": sd.get("failed_fees_lamports"), "sum_of_lines_WRONG": summed}}
