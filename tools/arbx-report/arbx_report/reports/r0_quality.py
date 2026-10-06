"""R0 Data quality (MEASUREMENT.md §6.3). Runs first; every other report cites it."""
from __future__ import annotations

from .. import legacy, streams
from . import cov, incomplete, section

CORE = ["ledger", "wallet", "attempts", "copies", "bundles", "outcomes", "decisions", "commits", "control"]
REPLAY = ["accounts", "journal"]
CHAIN = ["exec", "blocks", "slots", "slotidx", "txfetch", "txarr", "arrivals", "moves", "poh", "slots-feed", "alts",
         "leaders", "triggers", "predictions", "caps", "sims", "verify"]
SLOW = ["events", "status", "feedhealth", "resources", "keepalive", "snapshots", "recon"]
WITHIN_10_MIN_NS = 600 * 10 ** 9
WITHIN_60_S_NS = 60 * 10 ** 9


def run(seg, ctx: dict) -> dict:
    sec = section("R0", "Data quality")
    d = sec["data"]
    files = []
    unsupported = []
    for stream, fis in sorted(seg.files.items()):
        for fi in fis:
            streams.peek(fi)
            if fi.major is not None and not fi.legacy:
                try:
                    streams.check_version(stream, fi.major, fi.name)
                except streams.SchemaError as e:
                    unsupported.append(str(e))
            files.append({"file": fi.name, "stream": stream, "schema": fi.schema or ("v1" if fi.legacy else None),
                          "producer": (fi.header or {}).get("producer") if isinstance(fi.header, dict) else None})
    d["files"] = files
    if unsupported:
        d["unsupported_schema"] = unsupported
        incomplete(sec, "files with unknown major schema versions are refused")
    present = set(seg.files)
    if seg.legacy:
        d["format"] = "arb-lab v1 (legacy reader, MEASUREMENT §7)"
        d["not_comparable"] = {k: v for k, v in sorted(legacy.NOT_COMPARABLE.items()) if k in present or k == "meta"}
        d["recorder_streams_missing"] = [s for s in ("exec", "rivals", "txarr", "moves", "poh") if s not in present]
        if d["recorder_streams_missing"]:
            sec["caveats"].append("recorder streams missing (arb-lab ran with [record] off from w5h2-p3, W §8): "
                                  + ", ".join(d["recorder_streams_missing"]))
        _legacy_quality(seg, sec)
        return sec
    d["format"] = "arbx v2"
    d["missing_streams"] = {"core": [s for s in CORE if s not in present], "replay": [s for s in REPLAY if s not in present],
                            "chain": [s for s in CHAIN if s not in present], "slow": [s for s in SLOW if s not in present]}
    _drops(seg, sec)
    _replay_gaps(seg, sec, ctx)
    _exec_coverage(seg, sec, ctx)
    _other_coverage(seg, sec, ctx)
    _commits(seg, sec)
    _misc(seg, sec)
    return sec


def _legacy_quality(seg, sec):
    d = sec["data"]
    att = seg.attempts
    outs = seg.outcomes
    no_out = [a["attempt"] for a in att if a["attempt"] not in outs]
    d["attempts"] = len(att)
    d["attempts_without_outcome"] = {"n": len(no_out), "attempts": no_out[:50],
                                     "note": "in flight when the segment stopped; v1 never settled them"}
    se = {}
    for o in outs.values():
        e = (o.get("legacy") or {}).get("settle_error")
        if e:
            key = "sim_gated" if "sim_gated" in e else e[:60]
            se[key] = se.get(key, 0) + 1
    d["settle_errors"] = dict(sorted(se.items()))
    d["status_lines"] = len(seg.status)
    d["status_seq"] = "absent in v1 (lost lines cannot be detected)"


def _drops(seg, sec):
    d = sec["data"]
    man = seg.manifest
    if not man:
        incomplete(sec, "missing manifest.json: recorder drops unknown")
        return
    rows = []
    core_fault = []
    for s in man.get("streams") or []:
        rows.append({"stream": s.get("name"), "class": s.get("class"), "records_total": s.get("records_total"),
                     "dropped_total": s.get("dropped_total"), "queue_hwm": s.get("queue_hwm"), "queue_cap": s.get("queue_cap")})
        if s.get("class") == "core" and (s.get("dropped_total") or 0) > 0:
            core_fault.append(s.get("name"))
    d["recorder"] = sorted(rows, key=lambda r: r["stream"] or "")
    d["manifest_final"] = man.get("final")
    d["disk_actions"] = (man.get("disk") or {}).get("actions") or []
    if core_fault:
        d["core_drop_fault"] = core_fault
        sec["caveats"].append("SEGMENT FAULT: core stream drops (" + ", ".join(core_fault) + "); the segment cannot be reconciled")
    for s in rows:
        if s["class"] == "chain" and s["records_total"]:
            share = (s["dropped_total"] or 0) / (s["records_total"] + (s["dropped_total"] or 0))
            if share >= 0.0001:
                sec["caveats"].append(f"chain stream {s['stream']} dropped {share:.4%} (Stage-0 gate < 0.01%)")


def _replay_gaps(seg, sec, ctx):
    d = sec["data"]
    if ctx.get("quick"):
        d["replay_gaps"] = "skipped (--quick)"
        return
    if seg.has("accounts"):
        sc = streams.AccountsScan()
        n = 0
        d1 = set()
        first_seen: dict = {}
        for r in streams.iter_accounts(seg.stream_files("accounts"), keep_data=False, scan=sc):
            n += 1
            if r.txn:
                if r.src == 0:
                    d1.add(r.txn)
                if r.txn not in first_seen or r.t_recv_ns < first_seen[r.txn]:
                    first_seen[r.txn] = r.t_recv_ns
        ctx["d1"] = d1
        ctx["acct_first_seen"] = first_seen
        d["accounts"] = {"records": n, "gaps": [{"first_aseq": g[0], "n_lost": g[1]} for g in sc.gaps],
                         "unmarked_holes": [list(h) for h in sc.aseq_holes], "marks": _count(m["mark"] for m in sc.marks),
                         "errors": sc.errors[:20], "unknown_kinds": sc.unknown_kinds}
        if sc.gaps or sc.aseq_holes:
            sec["caveats"].append("accounts.bin has replay gaps: replay refuses those intervals (Stage-0 exit requires 0)")
    if seg.has("journal"):
        js = streams.JournalScan()
        n = sum(1 for _ in streams.iter_journal(seg.stream_files("journal"), js))
        d["journal"] = {"records": n, "gaps": [{"first_seq": g[0], "n_lost": g[1]} for g in js.gaps],
                        "unmarked_holes": [list(h) for h in js.seq_holes], "by_kind": dict(sorted(js.counts.items()))}
        if js.gaps or js.seq_holes:
            sec["caveats"].append("journal.bin has gaps: replay refuses those intervals")


def _wallet_vs_sigs(seg, ctx) -> dict:
    """Wallet transactions in wallet.jsonl against getSignaturesForAddress over the segment's slots (if online or
    cached in chain-cache/). Signatures the wallet stream lacks are misses (§6.3); the reverse is not a miss."""
    ch = ctx.get("chain")
    slots = [r.get("slot") for r in seg.wallet_rows if r.get("slot") is not None] + list(seg.slotidx)
    if ch is None or not seg.wallet or not slots:
        return {"status": "skipped (no chain access, wallet or slot range)"}
    from .. import chain as chainmod
    lo, hi = min(slots), max(slots)
    try:
        sigs = ch.signatures_for_address(seg.wallet, lo, hi)
    except chainmod.Offline:
        return {"status": "skipped (offline and not cached)"}
    have = {r.get("sig") for r in seg.wallet_rows}
    missing = sorted(r["signature"] for r in sigs if r.get("signature") not in have)
    return {"status": "checked", "slot_range": [lo, hi], "chain": len(sigs), "wallet_stream": len(have),
            "missing_from_wallet_stream": missing[:50], "missing_n": len(missing)}


def _q(xs, q):
    from .. import stats
    return stats.quantile(xs, q)


def _count(it):
    out: dict = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items()))


def _exec_coverage(seg, sec, ctx):
    """Coverage = records with full meta and idx within 10 minutes / |D1 u D2| (§4.14)."""
    d = sec["data"]
    if not seg.has("exec"):
        incomplete(sec, "missing stream: exec (coverage unknown)")
        return
    d1 = ctx.get("d1") or set()
    first_seen: dict = dict(ctx.get("acct_first_seen") or {})
    if ctx.get("d1") is None and seg.has("accounts"):
        incomplete(sec, "D1 (accounts.bin txn) not scanned (--quick): coverage uses D2 only")
    d2 = set()
    for s, row in seg.slotidx.items():
        for sig, _idx in row.get("tracked") or []:
            d2.add(sig)
            t = row.get("t_fetch_ns")
            if t is not None and (sig not in first_seen or t < first_seen[sig]):
                first_seen[sig] = t
    denom = d1 | d2
    by_venue: dict = {}
    by_found: dict = {}
    full10 = full60 = full_noidx = 0
    seen = set()
    for e in seg.iter_exec():
        sig = e.get("sig")
        if sig not in denom or sig in seen:
            continue
        seen.add(sig)
        full = e.get("keys") is not None and e.get("pre") is not None
        t0 = first_seen.get(sig)
        lag = (e.get("t") - t0) if (t0 is not None and e.get("t") is not None) else None
        has_idx = e.get("idx") is not None
        in10 = full and has_idx and (lag is None or lag <= WITHIN_10_MIN_NS)
        in60 = full and has_idx and lag is not None and lag <= WITHIN_60_S_NS
        full10 += in10
        full60 += in60
        full_noidx += bool(full and not has_idx)
        for v in e.get("venues") or ["unknown"]:
            b = by_venue.setdefault(v, [0, 0])
            b[0] += in10
        for fb in e.get("found_by") or ["unknown"]:
            b = by_found.setdefault(fb, [0, 0])
            b[0] += in10
    d["exec_coverage"] = {
        "denominator": {"d1_account_txn": len(d1), "d2_slotidx_tracked": len(d2), "union": len(denom)},
        "within_10min_with_idx": cov(full10, len(denom)), "within_60s_with_idx": cov(full60, len(denom)),
        "full_meta_without_idx": full_noidx,
        "by_venue_within_10min": {k: v[0] for k, v in sorted(by_venue.items())},
        "by_found_by_within_10min": {k: v[0] for k, v in sorted(by_found.items())},
        "gate": "coverage >= 99% and unseen share < 1% (PLAN §6)",
    }
    st = seg.status_agg
    now = st.get("now", {}) if isinstance(st, dict) else {}
    last_cov = next((s.get("coverage") for s in reversed(seg.status) if s.get("coverage")), None) or {}
    d["exec_coverage"]["unseen_share_sample_last"] = last_cov.get("unseen_share_sample")
    d["exec_coverage"]["status_watched_with_tx_pct_last"] = last_cov.get("watched_with_tx_pct")
    d["exec_coverage"]["need_rps"] = now.get("chainfetch.need_rps_now")
    d["exec_coverage"]["have_rps"] = now.get("chainfetch.have_rps_now")
    pct = d["exec_coverage"]["within_10min_with_idx"]["pct"]
    if pct is not None and pct < 99.0:
        sec["caveats"].append(f"exec coverage {pct}% is below the 99% gate: R4/R8/R9 see only part of the field")


def _other_coverage(seg, sec, ctx):
    d = sec["data"]
    att = seg.attempts
    n = len(att)
    with_verdict = sum(1 for a in att if seg.verdicts_by_attempt.get(a["attempt"]))
    with_leader = sum(1 for a in att if (a.get("leader") or {}).get("identity"))
    with_poh = 0
    for a in att:
        o = seg.outcomes.get(a["attempt"]) or {}
        if ((o.get("poh") or {}).get("trigger") or {}).get("ms") is not None:
            with_poh += 1
    bc = (ctx.get("blockctx") or {}).get("rows")
    d["attempt_coverage"] = {"attempts": n, "with_verdicts": cov(with_verdict, n), "with_leader": cov(with_leader, n),
                             "with_poh_trigger": cov(with_poh, n),
                             "blockctx_complete": cov(sum(1 for r in bc if r.get("complete")), len(bc)) if bc is not None else None}
    ev = seg.events
    kinds = _count(e.get("kind") for e in ev)
    d["events"] = kinds
    d["wallet_update_missing"] = kinds.get("wallet_update_missing", 0)
    d["wallet_vs_signatures_for_address"] = _wallet_vs_sigs(seg, ctx)
    d["jito_stream_down"] = kinds.get("jito_stream_down", 0)
    d["alt_give_up"] = kinds.get("alt_give_up", 0)
    slots = seg.jsonl("slots")
    confirmed = {s["slot"] for s in slots if s.get("status") == "confirmed"}
    have = set(seg.slotidx)
    mism = sum(((r.get("idx_check") or {}).get("mismatches") or 0) for r in seg.slotidx.values())
    d["slotidx"] = {"confirmed_slots": len(confirmed), "with_line": cov(len(confirmed & have), len(confirmed)),
                    "lines": len(have), "idx_check_mismatches": mism,
                    "status": _count(r.get("status") for r in seg.slotidx.values())}
    tf = seg.jsonl("txfetch")
    if tf:
        roles: dict = {}
        for r in tf:
            b = roles.setdefault(f"{r.get('role')}/{r.get('method')}", {"calls": 0, "errors": 0, "rate_limited": 0, "latency_ms": []})
            b["calls"] += 1
            b["errors"] += not r.get("ok")
            b["rate_limited"] += r.get("err") == "rate_limited"
            if r.get("latency_ms") is not None:
                b["latency_ms"].append(r["latency_ms"])
        d["txfetch"] = {k: {**{kk: v for kk, v in b.items() if kk != "latency_ms"}, "latency_ms_p50": _q(b["latency_ms"], 0.5),
                            "latency_ms_p99": _q(b["latency_ms"], 0.99)} for k, b in sorted(roles.items())}
    rs = seg.jsonl("resources")
    if rs:
        d["resources"] = {"lines": len(rs), "rss_bytes_max": max((r.get("rss_bytes_now") or 0) for r in rs),
                          "cpu_user_ms": sum(r.get("cpu_user_ms_delta") or 0 for r in rs),
                          "cpu_sys_ms": sum(r.get("cpu_sys_ms_delta") or 0 for r in rs),
                          "fs_free_bytes_min": min(((r.get("disk") or {}).get("fs_free_bytes_now") or 0) for r in rs)}
    ka = seg.jsonl("keepalive")
    if ka:
        ms = [k["ms"] for k in ka if k.get("ms") is not None]
        d["keepalive"] = {"n": len(ka), "errors": sum(1 for k in ka if k.get("error")), "rtt_ms_p50": _q(ms, 0.5),
                          "rtt_ms_p99": _q(ms, 0.99)}
    alts = seg.jsonl("alts")
    if alts:
        d["alts"] = _count(a.get("event") for a in alts)
    if seg.probe:
        subs = seg.probe.get("subs") or []
        d["probe"] = {"accepted": sorted(s.get("sub") for s in subs if s.get("accepted")),
                      "refused": sorted(s.get("sub") for s in subs if not s.get("accepted"))}
    fh = seg.jsonl("feedhealth")
    up: dict = {}
    for r in fh:
        u = up.setdefault(r.get("name") or str(r.get("feed")), [0, 0])
        u[1] += 1
        u[0] += bool(r.get("connected_now"))
    d["feed_uptime"] = {k: cov(v[0], v[1]) for k, v in sorted(up.items())}


def _commits(seg, sec):
    d = sec["data"]
    cm = seg.jsonl("commits")
    if not cm:
        return
    d["commits"] = {"groups": len([c for c in cm if not c.get("late")]), "by_w_src": _count(c.get("w_src") for c in cm if not c.get("late")),
                    "by_outcome": _count(c.get("outcome") for c in cm if not c.get("late")),
                    "late_member_lines": sum(1 for c in cm if c.get("late")),
                    "torn_suspect_decisions": sum(1 for x in seg.decisions if x.get("torn_suspect")),
                    "fork_priced_decisions": sum(1 for x in seg.decisions if x.get("fork_priced"))}


def _misc(seg, sec):
    d = sec["data"]
    m = seg.meta or {}
    d["clock"] = m.get("clock")
    st = seg.status_agg
    d["status_seq"] = st.get("seq") if isinstance(st, dict) else None
    if d["status_seq"] and d["status_seq"].get("gaps"):
        sec["caveats"].append(f"status.jsonl lost lines {d['status_seq']['gaps']}: delta sums are incomplete")
    finals = _count(o.get("final") for o in seg.outcomes.values())
    d["outcome_finals"] = finals
    d["unsettled"] = finals.get("unsettled", 0)
    d["amends"] = seg.amends
    rc = seg.jsonl("recon")
    # FT-001: a stop without its snapshot is a line of its own (`kind` stop_snapshot_failed, `ok` null), not a window;
    # a window is failed only when `ok` is false (null: skipped, `snapshot_incomplete`, the next snapshot closes it)
    stop_missing = [r for r in rc if r.get("kind") == "stop_snapshot_failed"]
    wins = [r for r in rc if r.get("kind") != "stop_snapshot_failed"]
    d["recon"] = {"windows": len(wins), "failed": sum(1 for r in wins if r.get("ok") is False)}
    if stop_missing:
        d["recon"]["stop_snapshot_missing"] = [r.get("why") for r in stop_missing]
    sn = seg.jsonl("snapshots")
    d["snapshots"] = {"n": len(sn), "slot_mismatch": sum(1 for s in sn if s.get("slot_mismatch"))}
    if d["recon"]["failed"]:
        sec["caveats"].append(f"{d['recon']['failed']} reconciliation window(s) failed")
    for why in d["recon"].get("stop_snapshot_missing", []):
        sec["caveats"].append(f"no stop snapshot ({why}): the next segment's first snapshot reconciles the window since the last good one")
