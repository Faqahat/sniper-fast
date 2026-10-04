"""R11 Census and offline experiments (X1 census, X3 sizes, X6 size fit). WP-12 builds them on WP-09's
`arbx quote` / `arbx replay`; until then the sections are marked incomplete, with the inputs that already exist."""
from __future__ import annotations

from .. import stats
from . import incomplete, section

CAPTURABLE = {"max_size_sol": 4.2, "min_route_age_ms": 354, "excluded_rungs": [0, 1]}


def run(seg, ctx: dict, which: str = "census") -> dict:
    sec = section("R11", {"census": "X1 census", "sizes": "X3 sizes", "sizefit": "X6 size fit"}.get(which, which))
    d = sec["data"]
    if which == "census":
        ages = [x.get("route_age_ms") for x in seg.decisions if x.get("route_age_ms") is not None]
        d["inputs_available"] = {"decisions": len(seg.decisions), "route_age_ms": stats.pct(ages),
                                 "rule": CAPTURABLE}
        incomplete(sec, "X1 needs every gap's winner rung from R4 (arbx quote, WP-09) and the census of WP-12")
    elif which == "sizes":
        incomplete(sec, "X3 summarises `arbx replay --reprice-sizes` (WP-09/WP-12)")
    elif which == "sizefit":
        sizes = [((a.get("tx") or {}).get("bytes")) for a in seg.attempts]
        sizes = [s for s in sizes if s is not None]
        d["tx_bytes"] = stats.pct(sizes)
        d["share_within_1232"] = round(sum(1 for s in sizes if s <= 1232) / len(sizes), 6) if sizes else None
        incomplete(sec, "X6 offline size fit over every evaluated route needs `arbx replay` (WP-09/WP-12); "
                        "only the sent attempts' byte sizes are shown")
    return sec
