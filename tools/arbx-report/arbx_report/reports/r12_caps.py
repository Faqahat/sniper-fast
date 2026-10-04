"""R12 Caps (MEASUREMENT.md §6.4): budget tiers deduplicated into gap episodes (consecutive opportunities on one route
within 5 slots, as arb-lab's seg.py did). The market's realised take comes from R4 when it is complete."""
from __future__ import annotations

from .. import stats
from . import incomplete, section

EPISODE_SLOTS = 5


def episodes(caps: list) -> list:
    ep = []
    last: dict = {}
    for c in sorted(caps, key=lambda c: (c.get("slot") or 0, c.get("id") or 0)):
        k = (c.get("buy"), c.get("sell"))
        e = last.get(k)
        if e and c["slot"] - e["slot_last"] <= EPISODE_SLOTS:
            e["slot_last"] = c["slot"]
            e["ids"].append(c.get("id"))
            for i, x in enumerate(c.get("caps") or []):
                if i < len(e["caps"]) and x[2] is not None and (e["caps"][i] is None or x[2] > e["caps"][i]):
                    e["caps"][i] = x[2]
        else:
            e = {"buy": c.get("buy"), "sell": c.get("sell"), "pair": f"{c.get('buy_venue')}>{c.get('sell_venue')}",
                 "mint": c.get("mint"), "slot": c.get("slot"), "slot_last": c.get("slot"), "ids": [c.get("id")],
                 "caps": [x[2] for x in c.get("caps") or []]}
            ep.append(e)
            last[k] = e
    return ep


def run(seg, ctx: dict) -> dict:
    sec = section("R12", "Caps")
    d = sec["data"]
    caps = seg.jsonl("caps")
    if not caps:
        return incomplete(sec, "missing stream: caps")
    tiers = [x[0] for x in caps[0].get("caps") or []]
    ep = episodes(caps)
    per = []
    for i, t in enumerate(tiers):
        nets = [e["caps"][i] for e in ep if i < len(e["caps"]) and e["caps"][i] is not None and e["caps"][i] > 0]
        per.append({"budget_sol": t, "episodes_positive": len(nets), "sum_best_net": sum(nets),
                    "summary": stats.money_summary(nets)})
    hours = seg.window.get("wall_hours")
    d["priced"] = len(caps)
    d["episodes"] = len(ep)
    d["tiers"] = per
    d["per_hour_basis"] = "wall hours"
    d["sum_best_net_per_hour"] = {str(p["budget_sol"]): (round(p["sum_best_net"] / hours) if hours else None) for p in per}
    pairs: dict = {}
    for e in ep:
        pairs[e["pair"]] = pairs.get(e["pair"], 0) + 1
    d["episodes_by_pair"] = dict(sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:15])
    incomplete(sec, "the market's realised take per episode needs R4 closers (arbx quote, WP-09)")
    sec["caveats"].append("caps are our own quotes at each budget, not what the market took")
    return sec
