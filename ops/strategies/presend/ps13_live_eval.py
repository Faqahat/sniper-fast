#!/usr/bin/env python3
# PRE-SEND LIVE probe evaluation (agent 10-25 PKT; ops/strategies/presend/LIVE.md). Read-only on the run's --dip-log JSONL files.
# For each server file (one engine run with --presend-shadow --presend-live, engine dip13):
#  (1) parity: the live T2 triggers vs the shadow's presend_arm (presend_live_parity records + the matched count in run_end);
#  (2) arming: triggers, armed windows, skips and disarms by reason;
#  (3) attempts: sent / not sent (why), results (ok / 6042 / deadline / ata_exists / other / unseen), send acks; per path and per
#      leader client;
#  (4) WHERE THEY LAND: the landing of each attempt that landed, relative to the dump (d: the biggest one-trade drop >= 2% in the 2
#      slots before it) and to its own crossing trade (x: the first trade at or below its limit): ms on the feed clock (rx), the
#      block-position clock (a: the shadow's clock), the first sighting on any feed and the leader's PoH clock; the trades between
#      the dump and us; ahead of / behind the "instant" bots (buys within 1 ms of the dump on the feed); per path and per client;
#  (5) fills: rate (windows and attempts), costs per fill (failed-attempt fees, the fill's fee + tip), P&L (realized from the
#      chain = payer deltas of the buy and the sells; curve P&L from the feed);
#  (6) LIVE vs SHADOW per window (same trigger): the shadow's rows a / b / c (fill, gross P&L, net at the cheap cost row) next to
#      the live window (attempts, fill, realized P&L).
# usage: python3 ps13_live_eval.py --jsonl dip_rN.jsonl [dip_ams_rN.jsonl] [--json OUT.json] [--from "MM-DD HH:MM" --to "MM-DD HH:MM"] (PKT)
import sys, json, time, argparse, calendar, collections, math

LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
def pk(s): return calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
def pkt(t): return time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 5 * 3600))
SOL = 1e9
FEE_CHEAP = (5000 + 60_000 * 1_000 / 1e6) / 1e9  # the study's cheap failed attempt (shadow status line); live: the records' own fees
TIP = 0.001

def pct(v, q):
    v = sorted(x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x)))
    if not v: return None
    k = (len(v) - 1) * q; f = math.floor(k); c = math.ceil(k)
    return v[int(k)] if f == c else v[f] + (v[c] - v[f]) * (k - f)

def dist(v, unit="ms"):
    v = [x for x in v if x is not None]
    if not v: return "n 0"
    p = [pct(v, q) for q in (0.1, 0.25, 0.5, 0.75, 0.9)]
    return f"n {len(v)}: p10 {p[0]:.1f} | p25 {p[1]:.1f} | p50 {p[2]:.1f} | p75 {p[3]:.1f} | p90 {p[4]:.1f} {unit}"

BUCKETS = [(-1e9, 0, "before it"), (0, 5, "0-5"), (5, 10, "5-10"), (10, 20, "10-20"), (20, 50, "20-50"), (50, 212, "50-212"), (212, 1e12, ">1 slot")]
def buckets(v):
    v = [x for x in v if x is not None]
    if not v: return "-"
    c = collections.Counter()
    for x in v:
        for lo, hi, n in BUCKETS:
            if lo <= x < hi: c[n] += 1; break
    return ", ".join(f"{n} {c[n]} ({100 * c[n] / len(v):.0f}%)" for _, _, n in BUCKETS if c[n])

def load(f, t_from, t_to):
    R = collections.defaultdict(list)
    for l in open(f):
        if '"ev"' not in l: continue
        if '"presend' not in l and '"run_start"' not in l and '"run_end"' not in l: continue
        try: o = json.loads(l)
        except Exception: continue
        t = o.get("t")
        if t_from and isinstance(t, (int, float)) and t > 1e15 and not (t_from <= t / 1e9 < t_to): continue
        R[o["ev"]].append(o)
    return R

def server_name(f, seen):
    s = "AMS" if "ams" in f.lower() else "FRA"
    return s if s not in seen else f"{s}:{f}"

def evaluate(f, R, out):
    starts, ends = R["run_start"], R["run_end"]
    cfg = next((o.get("presend_live") for o in starts if o.get("presend_live")), None)
    say(f"\n=== {f}")
    if not cfg: say("  no presend_live config in run_start: not a --presend-live run"); return
    say(f"  config: size {cfg['spend'] / SOL:.3f} SOL, k {cfg['k']}/slot, drop {cfg['drop']}, deadline +{cfg['deadline_slots']} slot(s), CU {cfg['cu_limit']} x {cfg['cu_price']} uL "
        f"(failed attempt {cfg['fail_fee']} lamports), routes {cfg['routes']}, caps {cfg['max_fills']} fills / {cfg['fee_budget'] / SOL:.4f} SOL fees, "
        f"{'DRY' if cfg['dry'] else 'REAL'}, create-slot {cfg['create_slot']}, one position {cfg['one_position']}")
    end = next((o.get("presend_live") for o in reversed(ends) if o.get("presend_live")), None)
    ts = [o["t"] / 1e9 for o in starts + ends if o.get("t")]
    hours = (max(ts) - min(ts)) / 3600 if len(ts) >= 2 else None
    if ts: say(f"  run {pkt(min(ts))} -> {pkt(max(ts))} PKT" + (f" ({hours:.2f} h)" if hours else ""))
    res = {"cfg": cfg, "hours": hours}
    # (1) parity
    par = collections.Counter(o["kind"] for o in R["presend_live_parity"])
    if end: say(f"  (1) PARITY live triggers vs the shadow's presend_arm: matched {end['parity']['matched']}, live-only {end['parity']['live_only']}, shadow-only {end['parity']['shadow_only']}")
    else: say(f"  (1) PARITY (no run_end): live-only {par['live_only']}, shadow-only {par['shadow_only']}")
    res["parity"] = end["parity"] if end else dict(par)
    # (2) arming
    arms = {o["w"]: o for o in R["presend_live_arm"]}
    skips = collections.Counter(o["why"] for o in R["presend_live_skip"])
    dis = {o["w"]: o for o in R["presend_live_disarm"]}
    dwhy = collections.Counter(o["why"] for o in dis.values())
    say(f"  (2) ARMING triggers {len(arms) + sum(skips.values())}: armed {len(arms)}, skipped {dict(skips)}; disarmed {dict(dwhy)}")
    res["arming"] = dict(armed=len(arms), skips=dict(skips), disarms=dict(dwhy))
    # (3) attempts
    att = {o["sig"]: o for o in R["presend_attempt"]}
    land = {o["sig"]: o for o in R["presend_attempt_land"]}
    dry = sum(1 for o in att.values() if o.get("dry"))
    rescnt = collections.Counter(o["res"] for o in land.values())
    say(f"  (3) ATTEMPTS built {len(att)} ({'dry, never sent: ' + str(dry) if dry else 'sent'}), results {dict(rescnt)}" + (f", not sent {end['not_sent']}, acks {end['acks']}" if end else ""))
    per = collections.defaultdict(collections.Counter)
    for s, a in att.items():
        l = land.get(s)
        for k in (("path", a["path"]), ("client", a["client"] or "?")):
            per[k]["sent"] += 1
            if l: per[k][l["res"]] += 1
    for k in sorted(per):
        c = per[k]; say(f"      {k[0]:6s} {k[1]:16s} sent {c['sent']:5d} | " + ", ".join(f"{r} {c[r]}" for r in ("ok", "6042", "deadline", "ata_exists", "other", "failed_unknown", "unseen") if c[r]))
    res["attempts"] = dict(built=len(att), dry=dry, results=dict(rescnt), per={f"{a}:{b}": dict(c) for (a, b), c in per.items()})
    # (4) landing timing
    L = [l for l in land.values() if l["res"] != "unseen" and l.get("slot") is not None]
    with_d = [l for l in L if l.get("d")]
    say(f"  (4) WHERE THE ATTEMPTS LANDED: {len(L)} landed ({len(with_d)} within 2 slots after a >= 2% dump)")
    for lab, key in (("after the dump, feed rx", "ms_after_d_rx"), ("after the dump, block clock", "ms_after_d_a"), ("after the dump, first sighting", "ms_after_d_first"),
                     ("after the dump, PoH", "ms_after_d_poh")):
        v = [l.get(key) for l in with_d]
        say(f"      {lab:32s} {dist(v)} | {buckets(v)}")
    xs = [l for l in L if l.get("x")]
    for lab, key in (("after its crossing trade, rx", "ms_after_x_rx"), ("after its crossing trade, block", "ms_after_x_a"), ("after its crossing trade, PoH", "ms_after_x_poh")):
        say(f"      {lab:32s} {dist([l.get(key) for l in xs])}")
    say(f"      send -> seen on the executed feed: {dist([l.get('ms_send_to_rx') for l in L])}; slots after the send: {dict(collections.Counter(l.get('slots_after_send') for l in L))}")
    say(f"      trades between the dump and us: {dist([l.get('n_between') for l in with_d], 'trades')}")
    inst = [l for l in with_d if l.get("ahead_of_instant") is not None]
    ahead = sum(1 for l in inst if l["ahead_of_instant"]); behind = len(inst) - ahead
    bots = collections.Counter(u for l in inst for u in (l.get("instant_before_us") or []) + (l.get("instant_after_us") or []))
    say(f"      instant bots (buys within 1 ms of the dump on the feed): on {len(inst)} landings; we were AHEAD of all of them {ahead}, behind {behind}; bots {dict(bots.most_common(8))}")
    for k in ("path", "client"):
        g = collections.defaultdict(list)
        for l in with_d: g[l.get(k) or "?"].append(l)
        for n in sorted(g): say(f"      by {k} {n:16s} after the dump (block clock): {dist([l.get('ms_after_d_a') for l in g[n]])}; ahead of instant {sum(1 for l in g[n] if l.get('ahead_of_instant'))}/{sum(1 for l in g[n] if l.get('ahead_of_instant') is not None)}")
    res["landing"] = dict(landed=len(L), after_dump=len(with_d), ms_after_d_a=[l.get("ms_after_d_a") for l in with_d], ms_after_d_poh=[l.get("ms_after_d_poh") for l in with_d],
                          ahead=ahead, behind=behind, bots=dict(bots))
    # (5) fills, costs, P&L
    fills = R["presend_live_fill"]; closes = {o["w"]: o for o in R["presend_live_close"]}; real = {o["w"]: o for o in R["presend_live_realized"]}
    fees_failed = sum(l.get("fee") or 0 for l in land.values() if l["res"] not in ("ok", "unseen"))
    fill_fee = sum(o.get("fee") or 0 for o in fills); tips = sum(o.get("tip") or 0 for o in fills)
    pnl = [o.get("pnl") for o in real.values() if o.get("pnl") is not None]
    curve = [o.get("curve_pnl") for o in closes.values() if o.get("curve_pnl") is not None]
    nf = len(fills)
    say(f"  (5) FILLS {nf} of {len(arms)} armed windows ({100 * nf / max(len(arms), 1):.1f}%), {len(att) / max(nf, 1):.0f} attempts per fill; late fills (window already over) "
        f"{sum(1 for o in fills if not o.get('window_open'))}; unsold {sum(1 for o in closes.values() if o.get('result') != 'sold')}")
    say(f"      costs: failed-attempt fees {fees_failed / SOL:.6f} SOL ({fees_failed / SOL / max(nf, 1):.6f} per fill), the fills' fees {fill_fee / SOL:.6f}, tips {tips / SOL:.6f}")
    say(f"      P&L: realized (chain: buy + sells payer deltas, incl. their fees / tips) {sum(pnl) / SOL:+.6f} SOL over {len(pnl)} fills; curve P&L (feed) {sum(curve) / SOL:+.6f}; "
        f"NET = realized - failed-attempt fees {(sum(pnl) - fees_failed) / SOL:+.6f} SOL" + (f" ({(sum(pnl) - fees_failed) / SOL / hours * 24:+.3f} per 24 h)" if hours else ""))
    whys = collections.Counter(o.get("exit_why") for o in closes.values())
    say(f"      exits {dict(whys)}; per fill realized {dist([x / SOL * 1000 for x in pnl], 'mSOL')}")
    for k in ("path", "client"):
        g = collections.defaultdict(list)
        for o in fills: g[o.get(k) or "?"].append(o)
        for n in sorted(g):
            ws = [o["w"] for o in g[n]]; p = [real[w]["pnl"] for w in ws if w in real and real[w].get("pnl") is not None]
            say(f"      by {k} {n:16s} fills {len(g[n])}, realized {sum(p) / SOL:+.6f} SOL")
    res["fills"] = dict(n=nf, fees_failed=fees_failed, fill_fee=fill_fee, tips=tips, realized=sum(pnl), curve=sum(curve), net=sum(pnl) - fees_failed, exits=dict(whys))
    # (6) live vs shadow, per window
    sh_arm = {}
    for o in R["presend_arm"]: sh_arm[(o["mint"], o["sig"], o["j"])] = o
    sh_fill = collections.defaultdict(dict); sh_exit = collections.defaultdict(dict)
    for o in R["presend_fill"]: sh_fill[o["w"]][o["row"]] = o
    for o in R["presend_exit"]: sh_exit[o["w"]][o["row"]] = o
    att_w = collections.Counter(a["w"] for a in att.values())
    fill_w = {o["w"]: o for o in fills}
    rows = collections.defaultdict(lambda: collections.Counter())
    tab = []
    for w, a in arms.items():
        tr = a["trig"]; s = sh_arm.get((tr["mint"], tr["sig"], tr["j"]))
        lf = w in fill_w; lp = real.get(w, {}).get("pnl")
        r = {"w": w, "mint": tr["mint"], "attempts": att_w.get(w, 0), "live_fill": lf, "live_pnl": lp, "shadow": s is not None}
        for row in ("a", "b", "c"):
            sf = s and sh_fill[s["w"]].get(row); se = s and sh_exit[s["w"]].get(row)
            r[f"shadow_{row}_fill"] = bool(sf); r[f"shadow_{row}_pnl"] = se["pnl"] if se else None
            rows[row][("live fill" if lf else "live none") + " / " + ("shadow fill" if sf else "shadow none")] += 1
        tab.append(r)
    for row in ("a", "b", "c"):
        say(f"  (6) LIVE vs SHADOW row {row} (+{ {'a': 0, 'b': 5, 'c': 10}[row]} ms) on the {len(arms)} live windows: {dict(rows[row])}")
    both = [r for r in tab if r["live_fill"] and r["shadow_c_fill"]]
    if tab:
        say(f"      gross P&L of the shadow's row-c fills on these windows {sum(r['shadow_c_pnl'] or 0 for r in tab):+.4f} SOL (net at the cheap row "
            f"{sum((r['shadow_c_pnl'] or 0) - (TIP + 2 * FEE_CHEAP) for r in tab if r['shadow_c_fill']):+.4f}) vs live realized {sum(r['live_pnl'] or 0 for r in tab) / SOL:+.4f} SOL; "
            f"both filled on {len(both)} window(s)")
    res["windows"] = tab
    out[f] = res

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", nargs="+", required=True); ap.add_argument("--json")
    ap.add_argument("--from", dest="t_from"); ap.add_argument("--to", dest="t_to")
    a = ap.parse_args()
    t_from = pk(a.t_from) if a.t_from else None; t_to = pk(a.t_to) if a.t_to else 4e9
    say(f"PRE-SEND LIVE evaluation ({', '.join(a.jsonl)})" + (f" {a.t_from} -> {a.t_to} PKT" if t_from else ""))
    out = {}
    for f in a.jsonl: evaluate(f, load(f, t_from, t_to), out)
    if a.json: json.dump(out, open(a.json, "w"), indent=1, default=float)
