#!/usr/bin/env python3
"""APEX-PROBE report: one line per trade (live) or per would-be buy (shadow) from apex_probe's JSONL records.

usage: python3 ops/apex_probe/report.py apex_probe.jsonl [more.jsonl ...] [--json]

Per trade: time (PKT), token GMGN link, create -> our tx first seen in the shreds (ms), slot delta (0 = the create slot),
index delta vs the create (same slot), buyers ahead of us (distinct wallets / their curve SOL), our rank among the buys
after the create, the realized P&L (actual balance changes of every landed tx of the trade), and why it failed if it did.
Times are PKT (UTC+5).
"""
import json, sys, statistics, collections, datetime

def pkt(ns):
    if not ns: return "-"
    return datetime.datetime.fromtimestamp(ns / 1e9, datetime.timezone(datetime.timedelta(hours=5))).strftime("%m-%d %H:%M:%S")

def load(paths):
    out = []
    for p in paths:
        with open(p) as f:
            for l in f:
                l = l.strip()
                if not l: continue
                try: out.append(json.loads(l))
                except Exception: pass
    return out

def fmt(x, nd=1):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args: print(__doc__); sys.exit(1)
    recs = load(args)
    by = collections.defaultdict(dict)
    sells = collections.defaultdict(list)
    shadow = {}
    attempts = []
    starts = [r for r in recs if r.get("ev") == "start"]
    for r in recs:
        ev = r.get("ev"); i = r.get("id")
        if ev == "buy_sent": by[i]["sent"] = r
        elif ev in ("buy_landed", "buy_failed"): by[i]["land"] = r
        elif ev == "position": by[i].setdefault("pos_" + r.get("src", "?"), r)
        elif ev == "realized": by[i]["pnl"] = r
        elif ev == "sell_landed": by[i]["sell"] = r
        elif ev in ("sell_sent", "sell_failed"): sells[i].append(r)
        elif ev == "buy_shadow": shadow.setdefault(i, {})["buy"] = r
        elif ev == "shadow_landscape": shadow.setdefault(i, {})["land"] = r
        elif ev == "attempt": attempts.append(r)
    rows = []
    for i in sorted(k for k in by if k is not None and k != 0):
        t = by[i]; s = t.get("sent", {}); l = t.get("land", {}); pf = (t.get("pos_feed") or {}).get("pos") or {}; pb = (t.get("pos_block") or {}).get("pos") or {}
        p = pf or pb
        row = {
            "id": i, "time": pkt(s.get("t")), "mint": s.get("mint") or l.get("mint"), "gmgn": s.get("gmgn") or l.get("gmgn"), "creator": s.get("creator"),
            "route": (s.get("route") or {}).get("route"), "client": (s.get("route") or {}).get("client"), "paths": len(s.get("paths") or []),
            "rx_to_sent_us": s.get("rx_to_sent_us"), "status": "landed" if l.get("ev") == "buy_landed" else (l.get("why") or "pending"),
            "create_to_land_ms": l.get("create_to_shred_ms"), "slot_delta": l.get("slot_delta"), "idx_delta": p.get("idx_delta"),
            "buyers_ahead": p.get("buyers_ahead"), "sol_ahead": (p.get("sol_ahead") or 0) / 1e9 if p else None, "rank": p.get("buy_rank"),
            "dev_buys": p.get("dev_buys_in_create"), "pos_src": "feed" if pf else ("block" if pb else None),
            "block_idx_delta": pb.get("idx_delta"), "block_buyers_ahead": pb.get("buyers_ahead"),
            "fill_x": l.get("fill_vs_expected"), "sell_tries": len([x for x in sells[i] if x.get("ev") == "sell_sent"]),
            "pnl_sol": (t.get("pnl") or {}).get("pnl", None), "err": l.get("err_line"),
        }
        if row["pnl_sol"] is not None: row["pnl_sol"] /= 1e9
        rows.append(row)
    if as_json:
        print(json.dumps({"trades": rows, "shadow": list(shadow.values())}, indent=1)); return
    if starts:
        s0 = starts[-1]
        print(f"run: mode {s0.get('mode')} payer {s0.get('payer')} watch {s0.get('watch')} size {s0.get('size', 0)/1e9} SOL routes {s0.get('routes')} hold {s0.get('hold_ms')} ms guard {s0.get('buy_guard')}")
    if rows:
        print(f"\n{'#':>3} {'time PKT':14} {'create->land ms':>15} {'slot+':>5} {'idx+':>5} {'ahead':>5} {'SOL ahead':>9} {'rank':>4} {'fill x':>6} {'P&L SOL':>9} status / token")
        for r in rows:
            print(f"{r['id']:>3} {r['time']:14} {fmt(r['create_to_land_ms']):>15} {fmt(r['slot_delta']):>5} {fmt(r['idx_delta']):>5} {fmt(r['buyers_ahead']):>5} "
                  f"{fmt(r['sol_ahead'], 3):>9} {fmt(r['rank']):>4} {fmt(r['fill_x'], 3):>6} {fmt(r['pnl_sol'], 4):>9} {r['status']}{' (' + r['err'] + ')' if r['err'] else ''}  {r['gmgn']}")
        landed = [r for r in rows if r["status"] == "landed"]
        ms = [r["create_to_land_ms"] for r in landed if r["create_to_land_ms"] is not None]
        same = [r for r in landed if r["slot_delta"] == 0]
        pnl = [r["pnl_sol"] for r in rows if r["pnl_sol"] is not None]
        print(f"\nbuys {len(rows)} | landed {len(landed)} | in the create slot {len(same)} | create->land ms median {fmt(statistics.median(ms) if ms else None)} "
              f"(min {fmt(min(ms) if ms else None)}, max {fmt(max(ms) if ms else None)}) | realized {sum(pnl):+.4f} SOL over {len(pnl)} trades")
        fails = collections.Counter(r["status"] for r in rows if r["status"] != "landed")
        if fails: print("not landed / failed:", dict(fails))
    if attempts:
        # per leader client: first-rate and cost per landed buy (v2 lanes: one copy per lane, at most one lands)
        pos = {}
        for i, t in by.items():
            for k in ("pos_feed", "pos_block"):
                rv = (t.get(k) or {}).get("rivals")
                if rv and i not in pos: pos[i] = rv
        print(f"\nATTEMPTS by leader client: {'client':20} {'n':>3} {'landed':>6} {'first':>5} {'reverted':>8} {'not seen':>8} {'cost SOL':>9} {'cost/landed mSOL':>16}")
        g = collections.defaultdict(list)
        for a in attempts: g[a.get("client") or "?"].append(a); g["*"].append(a)
        for c, v in sorted(g.items(), key=lambda x: (x[0] == "*", x[0])):
            landed = [a for a in v if a["outcome"] == "landed"]
            first = [a for a in landed if (pos.get(a["id"]) or {}).get("first_non_bundle")]
            rev = [a for a in v if a["outcome"] == "reverted"]
            cost = sum(a.get("cost_lamports") or 0 for a in v if a["outcome"] != "landed") / 1e9
            print(f"{'':27}{c:20} {len(v):>3} {len(landed):>6} {len(first):>5} {len(rev):>8} {len([a for a in v if a['outcome'] == 'not_seen']):>8} {cost:>9.4f} "
                  f"{(1e3 * cost / len(landed)) if landed else float('nan'):>16.2f}")
        codes = collections.Counter((c.get("err_ix"), c.get("err_code")) for a in attempts for c in a.get("copies", []) if c.get("outcome") == "reverted")
        if codes: print("revert codes (instruction, custom code):", dict(codes))
        lanes = collections.Counter((c["lane"], c["outcome"]) for a in attempts for c in a.get("copies", []))
        print("lanes x outcome:", dict(sorted(lanes.items())))
        print("(cost = what the non-landed attempts cost: reverts pay base fee + priority; a landed buy's round trip is in P&L)")
    if shadow:
        print(f"\nSHADOW would-be buys: {len(shadow)}")
        print(f"{'#':>3} {'time PKT':14} {'rx->signed us':>13} {'feed->hot':>9} {'window':>6} {'build':>5} {'bundle':>6} {'create idx':>10} {'buys same slot':>14} {'next slot':>9} {'dev buys':>8} route / token")
        rx = []
        for i in sorted(shadow):
            b = shadow[i].get("buy", {}); s = shadow[i].get("land", {})
            rx.append(b.get("rx_to_built_us"))
            print(f"{i:>3} {pkt(b.get('t')):14} {fmt(b.get('rx_to_built_us')):>13} {fmt(b.get('feed_to_hot_us')):>9} {fmt(b.get('bundle_window_us')):>6} {fmt(b.get('build_sign_us')):>5} {fmt(b.get('bundle_seen')):>6} {fmt(s.get('create_idx')):>10} {fmt(s.get('buy_txs_same_slot_after_create')):>14} "
                  f"{fmt(s.get('buy_txs_next_slot')):>9} {fmt(s.get('dev_buys_in_create')):>8} {(b.get('route') or {}).get('route')} {b.get('gmgn')}")
        rx = [x for x in rx if x is not None]
        if rx: print(f"rx->signed median {statistics.median(rx):.0f} us")
    # timing stages + the creator-bundle window (shadow and live buy records)
    buys = [r for r in recs if r.get("ev") in ("buy_shadow", "buy_sent")]
    if buys:
        def pq(k):
            v = sorted(x.get(k) for x in buys if isinstance(x.get(k), (int, float)))
            return "-" if not v else f"{v[len(v) // 2]}/{v[min(len(v) - 1, int(len(v) * 0.9))]}"
        print("\nstages p50/p90 us: " + " | ".join(f"{k} {pq(k)}" for k in ("feed_to_hot_us", "hot_to_decide_us", "bundle_window_us", "prep_us", "build_sign_us", "rx_to_built_us", "rx_to_first_write_us", "rx_to_sent_us", "q_at_dequeue")))
        wins = collections.defaultdict(list)
        for x in buys: wins[x.get("bundle_end") or "-"].append(x)
        print("bundle window by end: " + " | ".join(f"{e}: n {len(v)}, found bundle {sum(1 for x in v if (x.get('bundle_seen') or 0) > 0)}, waited p50 {sorted(x.get('bundle_waited_us') or 0 for x in v)[len(v) // 2]} us" for e, v in sorted(wins.items())))

    # APEX-3 entry score (--entry-filter log|on): every scored watched create (buys + skips), pass rate, scores
    scored = [r for r in recs if r.get("ev") in ("buy_shadow", "buy_sent", "create_seen") and isinstance(r.get("entry"), dict)]
    if scored:
        st = next((x for x in starts if x.get("entry_model")), {})
        em = st.get("entry_model") or {}
        print(f"\nentry score ({st.get('entry_filter')}; model {em.get('name')} sha {str(em.get('sha256'))[:12]} thr {em.get('thr')}; match {st.get('match')}): "
              f"{len(scored)} scored, pass {sum(1 for r in scored if r['entry'].get('pass'))}, gated skips {sum(1 for r in scored if r.get('skip') == 'entry_score')}")
        print(f"{'ev':11} {'mint':12} {'score':>7} {'pass':>4} {'dev':>6} {'bund':>6} {'nb':>3} {'u':>5} {'u_src':7} {'bund_src':13} {'n_hist':>6} skip")
        for r in scored:
            e = r["entry"]; x = e.get("x") or [None] * 11
            print(f"{r['ev']:11} {str(r.get('mint'))[:12]:12} {fmt(e.get('score'), 3):>7} {'Y' if e.get('pass') else 'n':>4} {fmt(x[0], 2):>6} {fmt(x[1], 2):>6} {fmt(x[2], 0):>3} "
                  f"{fmt(x[3], 2):>5} {str(e.get('u_src')):7} {str(e.get('bund_src')):13} {fmt(x[5], 0):>6} {r.get('skip') or ''}")

if __name__ == "__main__":
    main()
