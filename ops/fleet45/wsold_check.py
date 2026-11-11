#!/usr/bin/env python3
"""dip45 WHALE-SOLD tracker: offline checker (docs/dip45_fleet.md, section "WHALE-SOLD tracker").

  wsold_check.py --engine FRA_RUN.jsonl --fills AMS_RUN.jsonl [AMS_RUN2.jsonl ...]

--engine  the jsonl of the run with --presend-live-whale-sold-log on (e.g. the FRA no-key dry run): its presend_live_whale_sold records
--fills   jsonl(s) of LIVE runs with real fills (e.g. AMS r83): presend_live_arm (the trigger) + presend_live_fill + presend_live_realized

Join: a live T2 fill -> its window's arm -> the trigger (mint, whale, slot, idx) -> the engine's track of the same trigger (same chain
facts: the whale's sells do not depend on whose engine saw them). The whale's cumulative sold fraction of its arm-time bag BEFORE the
fill's position (slot, idx) is recomputed from the engine's "sell" records. A fill after the track's end (window end + 30 slots) or
with no track is "no answer". Prints real P&L by "whale >= 50% sold before our fill" yes / no (and >= 25%, net >= 50%), T2 only,
overall and per day (PKT). Also the engine's own tracks (crossing shares) and would-fills. Read-only; no network.
"""
import argparse, json, os, sys, collections, datetime

PKT = datetime.timezone(datetime.timedelta(hours=5))


def recs(path, ev):
    with open(path) as fh:
        for l in fh:
            if ev not in l: continue
            try: yield json.loads(l)
            except json.JSONDecodeError: continue


def load_engine(path):
    tracks, sells, fills, arms, fin = {}, collections.defaultdict(list), [], [], None
    for r in recs(path, "presend_live_whale_sold"):
        if r.get("ev") != "presend_live_whale_sold": continue
        st = r.get("stage")
        if st == "close": tracks[r["track"]] = r
        elif st == "sell": sells[r["track"]].append(r)
        elif st in ("fill", "shadow_fill"): fills.append(r)
        elif st == "arm": arms.append(r)
    for r in recs(path, "run_end"):
        if r.get("ev") == "run_end": fin = (r.get("presend_live") or {}).get("whale_sold")
    # open tracks at a crash: rebuild from the arm records (no close)
    for a in arms:
        if a["track"] not in tracks:
            tracks[a["track"]] = {"track": a["track"], "mint": a["mint"], "whale": a["whale"], "bag": a["bag"], "trig": a["trig"], "end_slot": a["end_slot"], "open": True}
    by_trig = collections.defaultdict(list)
    for t in tracks.values(): by_trig[(t["mint"], t["trig"][0])].append(t)
    for v in sells.values(): v.sort(key=lambda r: (r["slot"], r["idx"], r.get("j", 0)))
    return tracks, sells, fills, arms, by_trig, fin


def frac_before(track, sells, slot, idx):
    bag = track["bag"] or 0
    sold = sum(r["sold_tok"] for r in sells.get(track["track"], []) if (r["slot"], r["idx"]) < (slot, idx))
    return (sold / bag if bag else 0.0), sold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True); ap.add_argument("--fills", nargs="*", default=[])
    a = ap.parse_args()
    tracks, sells, efills, arms, by_trig, fin = load_engine(a.engine)
    if not tracks:
        print("no presend_live_whale_sold tracks in", a.engine, "(was --presend-live-whale-sold-log on?)"); return 1

    # ---- (1) the engine's tracks ----
    closed = [t for t in tracks.values() if not t.get("open")]
    n = len(closed)
    sh = lambda k: sum(1 for t in closed if t.get(k) is not None)
    print(f"== ENGINE {os.path.basename(a.engine)}: tracks {len(tracks)} (closed {n}), arms {len(arms)} "
          f"(live {sum(1 for x in arms if x['src'] == 'live')}, shadow {sum(1 for x in arms if x['src'] != 'live')}), sells {sum(len(v) for v in sells.values())}")
    if n:
        print(f"   whale sold anything by window end + 30 slots: {100*sh('first_sell')/n:.1f}%  >=25%: {100*sh('s25')/n:.1f}%  >=50%: {100*sh('s50')/n:.1f}%  100%: {100*sh('s100')/n:.1f}%")
        for k in ("first_sell_dslot", "dslot25", "dslot50"):
            v = sorted(t[k] for t in closed if t.get(k) is not None)
            if v: print(f"   {k:17s} n={len(v):5d} p25 {v[len(v)//4]} p50 {v[len(v)//2]} p75 {v[3*len(v)//4]}")
    allsells = [r for v in sells.values() for r in v if r.get("pre") is not None]
    if allsells: print(f"   sells seen on a pre-exec feed first: {100*sum(1 for r in allsells if r['pre'])/len(allsells):.1f}% of {len(allsells)} (backfilled excluded)")
    for st in ("fill", "shadow_fill"):
        g = collections.Counter((r.get("kind", "?").split(":")[0], bool(r.get("sold50"))) for r in efills if r["stage"] == st and r.get("track") is not None)
        if g: print(f"   engine {st:11s}: " + ", ".join(f"{k[0]} sold50={'Y' if k[1] else 'n'} {v}" for k, v in sorted(g.items())))
    if fin: print("   run_end whale_sold:", json.dumps(fin)[:600])

    # ---- (2) the join: live T2 fills x the engine's tracks ----
    if not a.fills: return 0
    s_lo = min(t["trig"][0] for t in tracks.values()); s_hi = max(t["end_slot"] for t in tracks.values())
    rows, miss = [], collections.Counter()
    for path in a.fills:
        larms, fills, pnl = {}, {}, collections.defaultdict(int)
        for r in recs(path, "presend_live_"):
            ev = r.get("ev")
            if ev == "presend_live_arm" and r.get("trig"): larms[r["w"]] = r
            elif ev == "presend_live_fill": fills[(r["w"], r["mint"])] = r
            elif ev == "presend_live_realized": pnl[(r["w"], r["mint"])] += r.get("pnl", 0)
        for k, f in fills.items():
            if (f.get("kind") or "t2").lower() != "t2": continue
            if k not in pnl: miss["no realized"] += 1; continue
            if not (s_lo <= f["slot"] <= s_hi): miss["outside the engine's slots"] += 1; continue
            arm = larms.get(f["w"])
            if not arm: miss["no arm record"] += 1; continue
            tr = arm["trig"]
            cand = [t for t in by_trig.get((tr["mint"], tr["slot"]), []) if t["whale"] == tr["wallet"]]
            cand = [t for t in cand if t["trig"][1] == tr["idx"]] or cand
            if not cand: miss["no engine track (engine did not arm this trigger)"] += 1; continue
            t = cand[0]
            if f["slot"] > t["end_slot"]: miss["fill after the track's end"] += 1; continue
            fr, sold = frac_before(t, sells, f["slot"], f.get("idx", 0))
            day = datetime.datetime.fromtimestamp(f["t"] / 1e9, PKT).strftime("%m-%d") if f.get("t") else "?"
            rows.append(dict(run=os.path.basename(path), w=f["w"], mint=f["mint"], pnl=pnl[k] / 1e9, frac=fr, s25=fr >= 0.25, s50=fr >= 0.50,
                             dslot=f["slot"] - tr["slot"], day=day))
    print(f"== JOIN live T2 fills x engine tracks (mint + trigger): {len(rows)} realized fills joined; not joined: {dict(miss)}")
    fmt = lambda v: f"n={len(v):4d} net={sum(v):+8.3f} per fill={1000*sum(v)/len(v):+7.1f} mSOL win={sum(1 for x in v if x > 0)/len(v):.2f}" if v else "n=   0"
    for col, lab in (("s50", "whale >=50% sold before our fill"), ("s25", "whale >=25% sold before our fill")):
        y = [r["pnl"] for r in rows if r[col]]; n_ = [r["pnl"] for r in rows if not r[col]]
        print(f"   {lab}: YES {fmt(y)} | no {fmt(n_)}" + (f" | diff {1000*(sum(y)/len(y)-sum(n_)/len(n_)):+.1f} mSOL/fill" if y and n_ else ""))
    print("   per day (PKT), whale >=50% sold before our fill:")
    days = collections.defaultdict(lambda: ([], []))
    for r in rows: days[r["day"]][0 if r["s50"] else 1].append(r["pnl"])
    for d, (y, n_) in sorted(days.items()):
        print(f"   day {d}: YES {fmt(y)} | no {fmt(n_)}")
    if rows:
        print("   if we had only taken the YES fills: net " f"{sum(r['pnl'] for r in rows if r['s50']):+.3f} vs all {sum(r['pnl'] for r in rows):+.3f} SOL "
              "(upper bound: the NO fills' windows might have filled later at a YES moment; the replay prices that, this table does not)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
