"""R3 Attempts and Jito (MEASUREMENT.md §6.4, §6.2 rules 4-6)."""
from __future__ import annotations

from .. import stats
from . import ACCEPT_NOT_LAND, LANDED_ONLY_CAVEAT, ratio, section
from .r2_funnel import first_verdicts

DELAY_BUCKETS = [(0, 5, "0-5"), (5, 10, "5-10"), (10, 20, "10-20"), (20, 50, "20-50"), (50, None, "50+")]


def delay_bucket(ms):
    if ms is None:
        return "unknown"
    for lo, hi, name in DELAY_BUCKETS:
        if ms >= lo and (hi is None or ms < hi):
            return name
    return "unknown"


def rtt_bucket(ms):
    if ms is None:
        return "unknown"
    for edge in (2, 5, 10, 25, 50, 100):
        if ms < edge:
            return f"<{edge}"
    return ">=100"


def send_delay_ms(seg, a: dict):
    """t_sent - t_first_shred (v2). v1 has no shred time: t_sent - st.rx (first arrival of the trigger)."""
    st = a.get("stages") or {}
    t_sent = st.get("t_sent")
    if t_sent is None:
        ts = [c.get("t_sent") for c in seg.copies_by_attempt.get(a["attempt"], []) if (c.get("t_sent") or 0) > 0]
        t_sent = min(ts) if ts else None
    t0 = st.get("t_first_shred") or (a.get("trigger") or {}).get("t_first_shred")
    basis = "first_shred"
    if t0 is None and seg.legacy:
        t0, basis = st.get("rx"), "v1_rx"
    if t_sent is None or t0 is None:
        return None, basis
    return (t_sent - t0) / 1e6, basis


def run(seg, ctx: dict) -> dict:
    sec = section("R3", "Attempts and Jito")
    d = sec["data"]
    den = seg.land_rate_denominator()
    sent = den["sent_ids"]
    fv = first_verdicts(seg)
    cells: dict = {}
    basis_seen = set()
    first_ms = []
    seqs: dict = {}
    acc_land: dict = {}
    lost = []
    bh: dict = {}
    qwait = []
    lambdas = []
    realised = []
    rate_limited = 0
    for a in seg.attempts:
        aid = a["attempt"]
        if aid not in sent:
            continue
        vs = seg.verdicts_by_attempt.get(aid) or []
        o = seg.outcomes.get(aid) or {}
        ms, basis = send_delay_ms(seg, a)
        basis_seen.add(basis)
        kind = (a.get("leader") or {}).get("kind") or "unknown"
        key = f"band={a.get('band')}|delay={delay_bucket(ms)}|leader={kind}"
        c = cells.setdefault(key, {"attempts": 0, "would_fail": 0})
        c["attempts"] += 1
        c["would_fail"] += any(v.get("outcome") == "would-fail" for v in vs)
        ts = [x.get("t_sent") for x in seg.copies_by_attempt.get(aid, []) if (x.get("t_sent") or 0) > 0]
        if vs and ts and vs[0].get("t_ns"):
            first_ms.append((vs[0]["t_ns"] - min(ts)) / 1e6)
        seq = ">".join(v.get("outcome") or "?" for v in vs) or "none"
        seqs[seq] = seqs.get(seq, 0) + 1
        accepted = any(v.get("outcome") == "accepted" for v in vs)
        landed = o.get("final") in ("landed_ok", "landed_fail")
        ld = a.get("leader") or {}
        for dim, val in (("kind", kind), ("region", ld.get("region") or "unknown"), ("rtt", rtt_bucket(ld.get("rtt_ms"))),
                         ("be_rtt", rtt_bucket(ld.get("be_rtt_ms")))):
            b = acc_land.setdefault(dim, {}).setdefault(val, {"attempts": 0, "accepted": 0, "landed": 0, "accepted_landed": 0})
            b["attempts"] += 1
            b["accepted"] += accepted
            b["landed"] += landed
            b["accepted_landed"] += accepted and landed
        our_tip = (a.get("tip") or {}).get("lamports") or (a.get("expected") or {}).get("tip")
        for v in vs:
            if v.get("outcome") == "lost-auction" and v.get("bid") is not None:
                lost.append({"bid": v["bid"], "our_tip": our_tip})
        age = (a.get("blockhash") or {}).get("age_slots")
        if age is not None:
            k = str(min(age, 150) // 10 * 10)
            b = bh.setdefault(k, {"attempts": 0, "blockhash_not_found": 0})
            b["attempts"] += 1
            b["blockhash_not_found"] += any(v.get("code") == "blockhash-not-found" for v in vs)
        q = a.get("queue") or {}
        if q.get("wait_us") is not None:
            qwait.append(q["wait_us"])
        if q.get("lambda") is not None:
            lambdas.append(q["lambda"])
        rate_limited += sum(1 for x in seg.copies_by_attempt.get(aid, []) if x.get("status") == 429)
        if o.get("final") == "landed_ok" and o.get("round_trip_on_chain") is not None:
            exp = o.get("round_trip_predicted") or (a.get("expected") or {}).get("gross")
            if exp:
                realised.append(o["round_trip_on_chain"] / exp)
    for c in cells.values():
        c["would_fail_rate"] = ratio(c["would_fail"], c["attempts"])
    d["would_fail_by_band_delay_leader"] = dict(sorted(cells.items()))
    d["send_delay_basis"] = sorted(basis_seen)
    if "v1_rx" in basis_seen:
        sec["caveats"].append("v1 send delay is measured from the trigger's first arrival (st.rx), not its first shred")
    d["time_to_first_verdict_ms"] = stats.pct(first_ms)
    d["verdict_sequences"] = dict(sorted(seqs.items(), key=lambda kv: (-kv[1], kv[0]))[:30])
    d["accepted_then_would_fail"] = sum(v for k, v in seqs.items() if "accepted>" in k and "would-fail" in k.split("accepted>", 1)[1])
    for dim in acc_land.values():
        for b in dim.values():
            b["accepted_to_landed"] = ratio(b["accepted_landed"], b["accepted"])
            b["land_rate"] = ratio(b["landed"], b["attempts"])
            b["land_rate_ci95"] = stats.wilson(b["landed"], b["attempts"])
    d["accepted_vs_landed"] = {k: dict(sorted(v.items())) for k, v in sorted(acc_land.items())}
    d["lost_auction"] = {"n": len(lost), "bid": stats.pct([x["bid"] for x in lost]),
                         "bid_over_our_tip": stats.pct([x["bid"] / x["our_tip"] for x in lost if x.get("our_tip")])}
    d["blockhash_age_slots"] = dict(sorted(bh.items(), key=lambda kv: int(kv[0])))
    d["queue_wait_us"] = stats.pct(qwait)
    d["lambda"] = stats.pct(lambdas)
    d["rate_limited_copies_429"] = rate_limited
    landed_n = sum(1 for aid in sent if (seg.outcomes.get(aid) or {}).get("final") in ("landed_ok", "landed_fail"))
    d["land_rate"] = {"landed": landed_n, "denominator_sent_attempts": len(sent), "rate": ratio(landed_n, len(sent)),
                      "ci95": stats.wilson(landed_n, len(sent)), "denominator_src": den.get("src")}
    wf = sum(1 for aid in sent if any(v.get("outcome") == "would-fail" for v in seg.verdicts_by_attempt.get(aid, [])))
    d["realised_over_expected_landed_only"] = {"n": len(realised), "ratio": stats.pct(realised),
                                               "beside_would_fail": {"would_fail_attempts": wf, "sent": len(sent),
                                                                     "rate": ratio(wf, len(sent))},
                                               "caveat": LANDED_ONLY_CAVEAT}
    d["first_verdict"] = {}
    for v in fv.values():
        d["first_verdict"][v] = d["first_verdict"].get(v, 0) + 1
    d["first_verdict"] = dict(sorted(d["first_verdict"].items()))
    sec["caveats"].extend([LANDED_ONLY_CAVEAT, ACCEPT_NOT_LAND])
    if seg.legacy:
        sec["caveats"].append("v1: no band, no leader telemetry, no blockhash age (nonce era)")
    return sec
