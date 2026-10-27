#!/usr/bin/env python3
"""DIP LANDING PROBE evaluator (engine dip14; ops/dip/speed/fixes/FIXES.md).

A probe = a buy that cannot fill (min tokens out = u64::MAX: pump 6042 on chain, tips revert) fired right after a real
in-envelope dump, through ONE forced send path (--dip-probe-paths, rotated), optionally only on some leader clients
(--dip-probe-clients). With --dip-probe-tipless on, every probe also sends a TIPLESS twin through the same path (D3).
Run the engine with --dip-clock2 so the timing records carry the block clocks.

usage:
  python3 probe_eval.py --jsonl dip_rN.jsonl [more.jsonl ...] [--log dip_rN.log ...] [--json out.json] [--propose]
                        [--from "MM-DD HH:MM"] [--to "MM-DD HH:MM"] (PKT)

Per path, and per path x leader class:
  probes; landed (the executed feed saw the failed tx, or a feed saw our tx); same-slot share (our tx in the dump's slot);
  landing ms after the dump, p10 / p50 / p90, on every clock:
    feed  = our tx's arrival on the executed feed - the dump's (probe_land.ms_after_dump_feed)
    first = our tx's first sighting on any feed - the dump's (timing)
    b400  = block position, slot x slot_ms + index / max(400, index + 1) x slot_ms (clock2)
    bmix  = the same with the real block size when above 400 (clock2)
    pos   = the fixed PoH: the PoH hash count before the tx / the slot's total (= its fraction of the block; clock2)
    ent   = our tx's entries-feed arrival - the dump's (clock2; the closest thing to the leader's own time since Alpenglow)
  our block index and its distance to the dump's; cost (landed fails x their fee).
D3 (tipless twins): per path, the tipped copies' landed rate vs the tipless ones', and the relays' answers to each (FAST-ACK
lines of the .log, by the probe's tag).
--propose: a ROUTES string per leader class from the results (paths with >= 15 probes, ordered by same-slot share, then
b400 p50; the 3 best + staked-rpc) -- for the owner to adopt at deploy time, not applied by anything.
"""
import argparse, json, re, sys, time, collections

CLASSES = ["bam", "harmonic", "jito", "fd", "agave", "other"]


def cls(c):
    c = c or ""
    if c in ("AgaveBam", "FireBAM"): return "bam"
    if c.startswith("Harmonic"): return "harmonic"
    if c == "JitoLabs": return "jito"
    if c in ("Firedancer", "Frankendancer"): return "fd"
    if c == "Agave": return "agave"
    if c == "": return "unknown"
    return "other"


def pct(v, qs=(10, 50, 90)):
    v = sorted(x for x in v if x is not None)
    if not v: return None
    return [round(v[min(len(v) - 1, int(round((len(v) - 1) * q / 100)))], 1) for q in qs]


def pkt_ns(s):
    # "MM-DD HH:MM" PKT (UTC+5) of the current year -> ns
    y = time.gmtime().tm_year
    t = time.strptime(f"{y}-{s}", "%Y-%m-%d %H:%M")
    return int((time.mktime(t) - time.timezone - 5 * 3600) * 1e9)


def load(paths, t_from, t_to):
    probes, lands, timing, starts = [], {}, {}, []
    for p in paths:
        for line in open(p, errors="replace"):
            if not line.startswith("{"): continue
            try: r = json.loads(line)
            except Exception: continue
            ev = r.get("ev")
            if ev == "run_start": starts.append(r)
            elif ev == "probe":
                t = r.get("t_fire", 0)
                if (t_from and t < t_from) or (t_to and t > t_to): continue
                probes.append(r)
            elif ev == "probe_land": lands[r["sig"]] = r
            elif ev == "timing" and r.get("kind") in ("probe", "probe_tipless"): timing[r["buy_sig"]] = r
    return probes, lands, timing, starts


def acks(logs):
    """FAST-ACK lines by tag: [(path, status, ms)]"""
    out = collections.defaultdict(list)
    rx = re.compile(r"FAST-ACK tag=(\d+) path=(\S+) ack_ms=([\d.]+) (?:status=(\S+)|ok=(\S+))(?: reply=(.*))?")
    for p in logs or []:
        for line in open(p, errors="replace"):
            m = rx.search(line)
            if m: out[int(m.group(1))].append((m.group(2), m.group(4) or ("ok" if m.group(5) == "true" else "refused"), float(m.group(3)), (m.group(6) or "")[:60]))
    return out


def path_of(route):
    route = route or ""
    if route.startswith("forced:"): return route[len("forced:"):].replace(":tipless", "")
    return route


def one(sig, probe, lands, timing):
    """the result of one copy (sig): landed, same slot, clocks, index"""
    l, tm = lands.get(sig), timing.get(sig)
    c2 = (tm or {}).get("clock2") or {}
    seen = l is not None or (tm is not None and tm.get("buy_first_rx") is not None)
    first = None
    if tm and tm.get("buy_first_rx") and tm.get("dump_first_rx"): first = (tm["buy_first_rx"] - tm["dump_first_rx"]) / 1e6
    buy_slot = c2.get("buy_slot") or (l or {}).get("slot")
    dump_slot = c2.get("dump_slot") or probe.get("slot")
    same = (buy_slot == dump_slot) if (seen and buy_slot is not None and dump_slot is not None) else None
    idx = c2.get("buy_idx") if c2.get("buy_idx") is not None else (l or {}).get("idx")
    didx = c2.get("dump_idx") if c2.get("dump_idx") is not None else probe.get("idx")
    return {"seen": seen, "same": same, "feed": (l or {}).get("ms_after_dump_feed"), "first": first, "b400": c2.get("land_ms_b400"), "bmix": c2.get("land_ms_bmix"),
            "pos": c2.get("land_ms_pos"), "ent": c2.get("land_ms_ent"), "idx": idx, "didx": didx if (same and idx is not None and didx is not None) else None,
            "fee": (l or {}).get("fee"), "err": (l or {}).get("err")}


def summarize(rows, fee_default):
    n = len(rows)
    seen = [r for r in rows if r["seen"]]
    same = [r for r in seen if r["same"] is not None]
    out = {"probes": n, "landed": len(seen), "landed_pct": round(100 * len(seen) / n, 1) if n else None,
           "same_slot_pct": round(100 * sum(1 for r in same if r["same"]) / len(same), 1) if same else None}
    for k in ("feed", "first", "b400", "bmix", "pos", "ent"):
        out[k + "_ms"] = pct([r[k] for r in seen if r["same"] or k in ("feed", "first", "ent")])
    out["idx"] = pct([r["idx"] for r in seen])
    out["idx_after_dump"] = pct([r["idx"] - r["didx"] for r in seen if r["didx"] is not None and r["idx"] is not None])
    out["cost_sol"] = round(sum((r["fee"] if r["fee"] is not None else fee_default) for r in seen) / 1e9, 6)
    out["errors"] = dict(collections.Counter((r["err"] or "?")[:40] for r in seen).most_common(4))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", nargs="+", required=True)
    ap.add_argument("--log", nargs="*")
    ap.add_argument("--json")
    ap.add_argument("--from", dest="t_from")
    ap.add_argument("--to", dest="t_to")
    ap.add_argument("--fee-lamports", type=int, default=505_000, help="fee of a landed probe when the record has none (5,000 + 100k CU x 5M uL)")
    ap.add_argument("--propose", action="store_true")
    a = ap.parse_args()
    probes, lands, timing, starts = load(a.jsonl, pkt_ns(a.t_from) if a.t_from else None, pkt_ns(a.t_to) if a.t_to else None)
    ack = acks(a.log)
    if not probes: print("no probe records"); return 1
    by = collections.defaultdict(list)          # (path, class) -> rows of the tipped copies
    tw = collections.defaultdict(list)          # path -> rows of the tipless twins
    tw_ack = collections.defaultdict(collections.Counter)
    tip_ack = collections.defaultdict(collections.Counter)
    for p in probes:
        path, c = path_of(p.get("route")), cls(p.get("client"))
        r = one(p["buy_sig"], p, lands, timing)
        by[(path, c)].append(r); by[(path, "all")].append(r)
        for (pth, st, ms, rep) in ack.get(p.get("tag", -1), []): tip_ack[path][st] += 1
        t = p.get("tipless") or {}
        if t.get("buy_sig"):
            tw[path].append(one(t["buy_sig"], p, lands, timing))
            for (pth, st, ms, rep) in ack.get(p.get("tipless_tag", -1), []): tw_ack[path][f"{st} {rep}".strip()] += 1
    res = {"probes": len(probes), "runs": [{k: s.get(k) for k in ("wallet", "t", "probe_x", "clock2")} for s in starts], "paths": {}, "d3": {}}
    print(f"DIP PROBES: {len(probes)} probes, {sum(1 for p in probes if one(p['buy_sig'], p, lands, timing)['seen'])} landed (tipped copies)")
    hdr = f"{'path':14} {'class':9} {'n':>4} {'land%':>6} {'same%':>6}  {'feed p10/50/90':>18} {'b400':>18} {'bmix':>18} {'pos (PoH)':>18} {'ent':>18} {'idx+':>14} {'cost':>9}"
    print(hdr)
    for (path, c), rows in sorted(by.items(), key=lambda x: (x[0][0], x[0][1] != "all", x[0][1])):
        s = summarize(rows, a.fee_lamports)
        res["paths"].setdefault(path, {})[c] = s
        f = lambda v: "/".join(str(x) for x in v) if v else "-"
        print(f"{path:14} {c:9} {s['probes']:>4} {s['landed_pct'] or 0:>6} {s['same_slot_pct'] if s['same_slot_pct'] is not None else '-':>6}  {f(s['feed_ms']):>18} {f(s['b400_ms']):>18} "
              f"{f(s['bmix_ms']):>18} {f(s['pos_ms']):>18} {f(s['ent_ms']):>18} {f(s['idx_after_dump']):>14} {s['cost_sol']:>9}")
    if tw:
        print("\nD3: tipped vs tipless copies of the same probes (a tipped copy that would revert dropped = landed only tipless)")
        for path, rows in sorted(tw.items()):
            st, s2 = summarize(by[(path, "all")], a.fee_lamports), summarize(rows, a.fee_lamports)
            res["d3"][path] = {"tipped": st, "tipless": s2, "tipped_acks": dict(tip_ack[path]), "tipless_acks": dict(tw_ack[path])}
            print(f"  {path:14} tipped landed {st['landed']}/{st['probes']} ({st['landed_pct']}%) | tipless landed {s2['landed']}/{s2['probes']} ({s2['landed_pct']}%) | "
                  f"tipless answers {dict(tw_ack[path].most_common(3))}")
    if a.propose:
        prop = {}
        for c in CLASSES:
            cand = [(p, d[c]) for p, d in res["paths"].items() if c in d and d[c]["probes"] >= 15 and d[c]["landed"] > 0]
            cand.sort(key=lambda x: (-(x[1]["same_slot_pct"] or 0), (x[1]["b400_ms"] or [0, 1e9])[1]))
            keep = [p for p, _ in cand[:3]]
            if "staked-rpc" not in keep and any(p == "staked-rpc" for p, _ in cand): keep.append("staked-rpc")
            if keep: prop[c] = keep
        routes = ";".join(f"{c}={'+'.join(v)}" for c, v in prop.items())
        res["proposal"] = routes
        print(f"\nPROPOSED ROUTES (owner's decision at deploy; classes without >= 15 probes keep today's): {routes or '(not enough probes)'}")
    if a.json: json.dump(res, open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
