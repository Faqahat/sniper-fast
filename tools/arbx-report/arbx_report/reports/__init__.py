"""Reports R0-R13 and the tables of MEASUREMENT.md §6.4. Every report is `run(seg, ctx) -> section` where a
section is a plain dict:

    {"id", "title", "complete": bool, "incomplete": [reason], "caveats": [text], "coverage": {...}, "data": {...}}

A section that cannot be computed from the files it needs says so in `incomplete`; it is never approximated
(§6.1 "Dependencies on the bot", §6.2 rule 8)."""
from __future__ import annotations

LANDED_ONLY_CAVEAT = ("landed-only: a bundle that overprices its gap fails its on-chain check and never lands, so "
                      "realised/expected over landed attempts cannot show overpricing (W §3); read it beside the "
                      "would-fail statistics")
ACCEPT_NOT_LAND = "acceptance is not landing: accepted -> landed is reported separately, by leader kind"


def section(sid: str, title: str) -> dict:
    return {"id": sid, "title": title, "complete": True, "incomplete": [], "caveats": [], "coverage": {}, "data": {}}


def incomplete(sec: dict, reason: str) -> dict:
    sec["complete"] = False
    if reason not in sec["incomplete"]:
        sec["incomplete"].append(reason)
    return sec


def need(seg, sec: dict, *streams_needed: str) -> bool:
    """Mark the section incomplete for each missing stream; True when all are present."""
    ok = True
    for s in streams_needed:
        if not seg.has(s):
            incomplete(sec, f"missing stream: {s}")
            ok = False
    return ok


def ratio(a, b):
    if a is None or not b:
        return None
    return round(a / b, 6)


def cov(have: int, total: int) -> dict:
    return {"have": have, "total": total, "pct": (round(100.0 * have / total, 3) if total else None)}
