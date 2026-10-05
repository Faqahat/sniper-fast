"""R8 Predictions and accuracy (MEASUREMENT.md §6.4).

In-bot hints are scored against the pre-state version (`exact`); the v1-style at-hint rate is shown beside it and
`pre_state_unknown` is counted, never scored, as are swaps that did not quote (`unquotable`, and `refused` by
arbx-sizing's reason) and exact-out swaps solved through exact-in quotes (`exact_out_solved`: out of the rate). Every-swap scoring and the closer check need `arbx quote` (WP-09)."""
from __future__ import annotations

from .. import stats
from . import LANDED_ONLY_CAVEAT, incomplete, ratio, section


def _v1_exact(p: dict):
    if "match" in p:
        return bool(p["match"])
    if "err0" in p and "err1" in p:
        return p["err0"] == 0 and p["err1"] == 0
    return None


def run(seg, ctx: dict) -> dict:
    sec = section("R8", "Predictions and accuracy")
    d = sec["data"]
    preds = seg.jsonl("predictions")
    by: dict = {}
    pools: dict = {}
    q: dict = {}
    for p in preds:
        v = p.get("venue") or "unknown"
        b = by.setdefault(v, {"n": 0, "scored": 0, "exact": 0, "pre_state_unknown": 0, "unquotable": 0, "refused": {},
                              "exact_out_solved": 0, "exact_out_solved_exact": 0, "hint_scored": 0, "hint_exact": 0,
                              "dlmm_bins_checked": 0, "dlmm_bins_exact": 0})
        b["n"] += 1
        if seg.v1("predictions"):
            e = _v1_exact(p)
            if e is not None:
                b["hint_scored"] += 1
                b["hint_exact"] += e
            continue
        # WP-16: a null `exact` is a lost pre-state only when `pre_state.known` is false; with a known pre-state the
        # swap did not quote (`refused` names arbx-sizing's reason: MEASUREMENT §4.34). An exact-out swap solved through
        # exact-in quotes (`exact_out_model` "solved") is not the venue's own rounding: counted apart, out of the rate
        if p.get("exact") is None:
            if (p.get("pre_state") or {}).get("known") is False:
                b["pre_state_unknown"] += 1
            elif p.get("refused"):
                b["refused"][p["refused"]] = b["refused"].get(p["refused"], 0) + 1
            else:
                b["unquotable"] += 1
        elif p.get("exact_out_model") == "solved":
            b["exact_out_solved"] += 1
            b["exact_out_solved_exact"] += bool(p["exact"])
        else:
            b["scored"] += 1
            b["exact"] += bool(p["exact"])
        h = p.get("hint") or {}
        if h.get("exact") is not None:
            b["hint_scored"] += 1
            b["hint_exact"] += bool(h["exact"])
        db = p.get("dlmm_bins") or {}
        b["dlmm_bins_checked"] += db.get("checked") or 0
        b["dlmm_bins_exact"] += db.get("exact") or 0
        if p.get("window_exact_pct") is not None:
            pools[p.get("pool")] = p["window_exact_pct"]
        if p.get("quarantine_action"):
            q[p["quarantine_action"]] = q.get(p["quarantine_action"], 0) + 1
    for b in by.values():
        b["exact_rate_pre_state"] = ratio(b["exact"], b["scored"])
        b["exact_rate_at_hint"] = ratio(b["hint_exact"], b["hint_scored"])
    d["by_venue"] = dict(sorted(by.items()))
    if seg.v1("predictions"):
        sec["caveats"].append("v1 predictions were made at hint time from the store: an earlier write to the pool in the "
                              "same slot makes a correct prediction look inexact (DAMM v2 87% in res-code §3)")
    else:
        d["worst_pools_window_exact_pct"] = sorted(([k, v] for k, v in pools.items()), key=lambda x: (x[1], x[0]))[:10]
        d["quarantine_actions"] = dict(sorted(q.items()))
    # realised against predicted on landed attempts (rule 6 caveat)
    rt = []
    legs = []
    for o in seg.outcomes.values():
        if o.get("final") != "landed_ok":
            continue
        if o.get("round_trip_on_chain") is not None and o.get("round_trip_predicted"):
            rt.append(o["round_trip_on_chain"] - o["round_trip_predicted"])
        dl, pr = o.get("delivered"), o.get("predicted")
        if dl and pr and len(dl) == len(pr):
            legs.append(all(x == y for x, y in zip(dl, pr)))
    d["landed_round_trip_minus_predicted"] = {**stats.pct(rt), "within_2_lamports": sum(1 for x in rt if abs(x) <= 2),
                                              "caveat": LANDED_ONLY_CAVEAT}
    d["landed_legs_exact"] = {"n": len(legs), "exact": sum(legs)}
    incomplete(sec, "every-swap scoring (aggregator-routed swaps included) and the closer check need `arbx quote` (WP-09)")
    return sec
