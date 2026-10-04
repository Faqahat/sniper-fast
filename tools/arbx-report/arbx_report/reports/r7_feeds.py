"""R7 Feeds (MEASUREMENT.md §6.4): uptime, reconnects, messages; first-arrival shares and lead times; dead feeds;
provider lag; PoH completeness per feed. Works on arb-lab's txarr.log and slots.log too."""
from __future__ import annotations

from .. import counters, stats, streams
from . import ratio, section


def run(seg, ctx: dict) -> dict:
    sec = section("R7", "Feeds")
    d = sec["data"]
    names = seg.feeds or []
    fh = seg.jsonl("feedhealth")
    if fh:
        by: dict = {}
        for r in fh:
            by.setdefault(r.get("name") or str(r.get("feed")), []).append(r)
        out = {}
        for name, lines in sorted(by.items()):
            agg = counters.aggregate(lines)
            out[name] = {"lines": len(lines), "connected_share": ratio(sum(1 for x in lines if x.get("connected_now")), len(lines)),
                         "reconnects": agg["total"].get("reconnects_total"), "errors": agg["total"].get("errors_total"),
                         "packets": agg["delta"].get("packets_delta"), "txs": agg["delta"].get("txs_delta"),
                         "forwarded": agg["delta"].get("forwarded_delta"), "first_arrivals": agg["delta"].get("first_arrivals_delta"),
                         "channel_drops": agg["delta"].get("channel_drops_delta"), "udp_drops": agg["delta"].get("udp_drops_delta"),
                         "lead_ms_p50_of_intervals": stats.quantile([x["lead_ms"]["p50"] for x in lines if (x.get("lead_ms") or {}).get("p50") is not None], 0.5),
                         "provider_lag_ms_p50_of_intervals": stats.quantile([x["provider_lag_ms"]["p50"] for x in lines if (x.get("provider_lag_ms") or {}).get("p50") is not None], 0.5)}
        d["feedhealth"] = out
    if seg.has("txarr") and not ctx.get("quick"):
        n = 0
        first: dict = {}
        delivered: dict = {}
        delays: dict = {}
        for t in streams.iter_txarr(seg.stream_files("txarr")):
            n += 1
            for i, v in enumerate(t["d"]):
                if v is None:
                    continue
                delivered[i] = delivered.get(i, 0) + 1
                if v == 0:
                    first[i] = first.get(i, 0) + 1
                else:
                    h = delays.setdefault(i, {})
                    h[v] = h.get(v, 0) + 1
        k = max(list(delivered) + [len(names) - 1, -1]) + 1
        rows = {}
        for i in range(k):
            nm = names[i] if i < len(names) else f"feed{i}"
            rows[nm] = {"delivered": delivered.get(i, 0), "delivered_share": ratio(delivered.get(i, 0), n),
                        "first": first.get(i, 0), "first_share": ratio(first.get(i, 0), n),
                        "behind_first_us": stats.pct_counts(delays.get(i, {}))}
        d["txarr"] = {"signatures": n, "feeds": rows, "dead_feeds": [nm for nm, r in rows.items() if r["delivered"] == 0]}
        if d["txarr"]["dead_feeds"]:
            sec["caveats"].append("dead feeds (delivered nothing): " + ", ".join(d["txarr"]["dead_feeds"]))
    if seg.has("slots-feed"):
        per: dict = {}
        for r in streams.iter_slots_feed(seg.stream_files("slots-feed")):
            f = r["feed"]
            b = per.setdefault(f, {"slots": 0, "valid": 0, "poh_complete": 0, "poh_known": 0, "ticks": []})
            b["slots"] += 1
            b["valid"] += bool(r.get("valid"))
            if r.get("poh_complete") is not None:
                b["poh_known"] += 1
                b["poh_complete"] += bool(r["poh_complete"])
            if r.get("ticks") is not None:
                b["ticks"].append(r["ticks"])
        out = {}
        for f, b in sorted(per.items()):
            nm = names[f] if isinstance(f, int) and 0 <= f < len(names) else str(f)
            out[nm] = {"slots": b["slots"], "valid_share": ratio(b["valid"], b["slots"]),
                       "poh_complete_share": ratio(b["poh_complete"], b["poh_known"]) if b["poh_known"] else None,
                       "ticks_p50": stats.quantile(b["ticks"], 0.5)}
        d["slots_feed"] = out
        if seg.legacy:
            sec["caveats"].append("v1 slots.log: entries feeds only; `valid` = 0 when the feed joined the slot midway")
    if not d:
        sec["complete"] = False
        sec["incomplete"].append("no feed streams (feedhealth, txarr, slots-feed)")
    return sec
