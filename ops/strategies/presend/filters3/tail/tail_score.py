#!/usr/bin/env python3
"""FILTERS-3 TAIL scorer (FROZEN 11-03). Reads ONE run's presend.jsonl (read-only), rebuilds every LIVE position, computes the
signing-time features and prints what each TAIL guard blocks and the money (a blocked trade saves exactly its realized P&L).

usage: tail_score.py RUN.presend.jsonl [--seed creator_seed.json] [--seed-out new_seed.json] [--from NS] [--until NS] [--json out.json] [--list]
  --seed      creator ledger at the run's start: {creator: [[t_known_ns, pnl_sol], ...]} (FROZEN seed = all runs 37..42)
  --seed-out  write the seed + this run's positions (to chain runs in time order)
  --from/--until  only positions whose fill t (ns, record clock) is in [from, until) (the r42 DEV / VAL split)

GUARDS (each alone; UNION = any of them, breaker sequential over the trades the union lets through):
  G1 CREATOR : skip when the token's creator (arm ann.creator) has a realized P&L sum <= -0.10 SOL over OUR past positions on its
               tokens (seed + this run; a position counts once its sell landed + 4 s).                         [needs ledger state]
  G2 CONC    : skip when the OTHER holders (>= 2% of supply; not the whale / re-arm dumper, not us) hold >= 35% in total at signing.
  G3 FRESH   : skip when the other holders with <= 1 hold on record (fresh wallets) hold >= 35% in total at signing. (ATTACK guard)
  G4 BREAKER : after 2 realized losses <= -0.20 SOL known within 10 min, no new trades for 30 min.                (ATTACK guard)
  REC        = G1 or G3 or G4 (the recommended set; breaker sequential over the trades REC lets through)
  E  CONC_HALF (ESTIMATE): G2's trades at half size instead of skipped: pnl_half = (pnl + c)/2 - c, c = the trip's fixed tx costs.
Signing-time holders: the fill's ann.holders (>= 2%, at our landing just before our buy) with the sells that happened after signing
added back (the crossing dump `d` and `between` of the filled attempt's landing record; SOL / the price just before our buy); a
seller gone by landing is added with its restored holding (age / holds unknown -> never counted fresh)."""
import sys, json, collections
from datetime import datetime, timezone, timedelta
PKT = timezone(timedelta(hours=5))
SUP = 1e15
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
CR_MAX, CONC_MIN, FRESH_MIN = -0.10, 35.0, 35.0
BRK_N, BRK_L, BRK_W, BRK_P = 2, 0.20, 10 * 60e9, 30 * 60e9
LAG = 4_000_000_000

def arg(k, d=None):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d

def load(src):
    arm, fill, close, real, tape = {}, {}, {}, collections.defaultdict(float), collections.defaultdict(list)
    t0, t1 = None, None
    for line in open(src, errors="replace"):
        if '"ev":"presend_live_' not in line and '"ev":"run_start"' not in line: continue
        d = json.loads(line); e = d["ev"]
        if "t" in d and isinstance(d["t"], int):
            t0 = d["t"] if t0 is None else min(t0, d["t"]); t1 = d["t"] if t1 is None else max(t1, d["t"])
        if e == "run_start": continue
        m = d.get("mint") or (d.get("trig") or {}).get("mint")
        k = (d.get("w"), m)
        if e == "presend_live_arm": arm[k] = d
        elif e == "presend_live_fill": fill.setdefault(k, d)
        elif e == "presend_live_close": close[k] = d
        elif e == "presend_live_realized": real[k] += d["pnl"]
        elif e == "presend_live_tape": tape[m].append(d)
    sigs = {f["sig"]: k for k, f in fill.items()}
    att, land = {}, {}
    for line in open(src, errors="replace"):
        if '"ev":"presend_attempt' not in line: continue
        i = line.find('"sig":"'); s = line[i + 7:line.find('"', i + 7)]
        if s not in sigs: continue
        d = json.loads(line)
        (att if d["ev"] == "presend_attempt" else land)[s] = d
    pos = []
    for k, f in fill.items():
        if k not in real: continue
        pos.append({"w": k[0], "mint": k[1], "pnl": real[k] / 1e9, "t": f["t"], "arm": arm.get(k) or {}, "fill": f,
                    "att": att.get(f["sig"], {}), "land": land.get(f["sig"], {}), "close": close.get(k, {})})
    pos.sort(key=lambda p: p["t"])
    return pos, t0, t1

def restore(at, L):
    """tokens (% of supply) each wallet sold AFTER signing (the crossing dump d + the trades between it and our buy), on the
    constant-product curve from the filled attempt's signing state (vsol, vtok); buys move the curve too"""
    add = collections.defaultdict(float)
    V, K = float(at.get("vsol") or 0), float(at.get("vtok") or 0)
    xs = [x for x in [L.get("d")] + list(L.get("between") or []) if x]
    xs.sort(key=lambda x: (x.get("slot", 0), x.get("idx", 0)))
    for x in xs:
        s = float(x.get("sol") or 0)
        if V <= 0 or K <= 0: break
        if x.get("buy"):
            K2 = V * K / (V + s); V, K = V + s, K2
        elif s < V:
            K2 = V * K / (V - s); add[x["user"][:8]] += (K2 - K) / SUP * 100.0; V, K = V - s, K2
    return add

def feats(p):
    a, f, at, L = p["arm"], p["fill"], p["att"], p["land"]
    fa = f.get("ann") or {}
    kind = a.get("kind") or "t2"
    tr = a.get("trig") or {}; du = a.get("dump") or {}
    whale = (tr.get("wallet") if kind == "t2" else du.get("seller")) or ""
    F = {"kind": kind, "creator": (a.get("ann") or {}).get("creator"), "whale": whale, "has_holders": fa.get("holders") is not None,
         "ts": at.get("t") or f["t"]}
    if not F["has_holders"]: return F
    add = restore(at, L)
    hs = []
    for h in fa["holders"]:
        hs.append({"w": h["w"], "pct": h["pct"] + add.pop(h["w"][:8], 0.0), "n": h.get("n") or 0, "age": h.get("age")})
    # a seller gone by landing: only as much as the curve's sold supply leaves room for (a wallet that never bought on the
    # curve - tokens moved to it - was never in the engine's holder view)
    vt = (at.get("vtok") or 0)
    room = ((1073e12 - vt) / SUP * 100.0 if vt else 100.0) - sum(h["pct"] for h in hs)
    for w8, pct in sorted(add.items(), key=lambda kv: -kv[1]):
        pct = min(pct, max(0.0, room)); room -= pct
        if pct >= 2.0: hs.append({"w": w8, "pct": pct, "n": None, "age": None})
    oth = [h for h in hs if h["w"][:8] != whale[:8] and h["w"] not in OURS]
    F["sum_oth"] = sum(h["pct"] for h in oth)
    F["sum_fresh"] = sum(h["pct"] for h in oth if h["n"] is not None and h["n"] <= 1)
    F["holders"] = " ".join(f"{h['w'][:6]}:{h['pct']:.1f}/n{h['n']}" for h in sorted(oth, key=lambda h: -h["pct"])[:7])
    return F

def known_t(p):
    sl = (p["close"].get("sell_land") or [None, None, None])
    return (sl[2] if len(sl) > 2 and sl[2] else p["t"] + 1_000_000_000) + LAG

def fixed_cost(p):
    f, c = p["fill"], p["close"]
    return (f.get("fee") or 0) / 1e9 + (f.get("tip") or 0) / 1e9 + sum((s[2] if len(s) > 2 else 0) for s in (c.get("sell_sigs") or [])) / 1e9

def main():
    src = sys.argv[1]
    seed = json.load(open(arg("--seed"))) if arg("--seed") else {}
    led = collections.defaultdict(list, {c: [tuple(x) for x in v] for c, v in seed.items()})
    lo, hi = int(float(arg("--from", 0))), int(float(arg("--until", 9e18)))
    pos, t0, t1 = load(src)
    allpos = pos
    pos = [p for p in pos if lo <= p["t"] < hi]
    hrs = (min(t1, hi) - max(t0, lo)) / 3.6e12
    G = ["G1_CREATOR", "G2_CONC", "G3_FRESH", "G4_BREAKER", "UNION", "REC"]
    blk = {g: [] for g in G}
    brk_alone = {"ev": [], "until": 0}; brk_u = {"ev": [], "until": 0}; brk_r = {"ev": [], "until": 0}
    pending = []  # (t_known, creator, pnl) of this run's positions
    # ledger events from positions of this run BEFORE the window (r42 VAL: DEV part of the same run) are past data too
    for p in allpos:
        if p["t"] < lo:
            c = (p["arm"].get("ann") or {}).get("creator")
            if c: pending.append((known_t(p), c, p["pnl"]))
    rows = []
    def brk(state, ts):
        bad = [t for t, v in state["ev"] if ts - BRK_W <= t <= ts and v <= -BRK_L]
        if len(bad) >= BRK_N: state["until"] = max(state["until"], max(bad) + BRK_P)
        return ts < state["until"]
    for p in pos:
        F = feats(p); ts = F["ts"]
        for t, c, v in [x for x in pending if x[0] <= ts]: led[c].append((t, v))
        pending = [x for x in pending if x[0] > ts]
        crs = sum(v for t, v in led.get(F["creator"], []) if t <= ts) if F["creator"] else 0.0
        g1 = bool(F["creator"]) and crs <= CR_MAX
        g2 = F["has_holders"] and F["sum_oth"] >= CONC_MIN
        g3 = F["has_holders"] and F["sum_fresh"] >= FRESH_MIN
        g4 = brk(brk_alone, ts)
        if not g4: brk_alone["ev"].append((known_t(p), p["pnl"]))
        u = g1 or g2 or g3 or brk(brk_u, ts)
        if not u: brk_u["ev"].append((known_t(p), p["pnl"]))
        rc = g1 or g3 or brk(brk_r, ts)
        if not rc: brk_r["ev"].append((known_t(p), p["pnl"]))
        for g, b in zip(G, (g1, g2, g3, g4, u, rc)):
            if b: blk[g].append(p)
        rows.append({"t": p["t"], "mint": p["mint"], "kind": F["kind"], "pnl": p["pnl"], "cr_ledger": crs, "sum_oth": F.get("sum_oth"),
                     "sum_fresh": F.get("sum_fresh"), "g": [g for g, b in zip(G, (g1, g2, g3, g4, u, rc)) if b], "fixed": fixed_cost(p), "holders": F.get("holders")})
        c = F["creator"]
        if c: pending.append((known_t(p), c, p["pnl"]))
    base = [r["pnl"] for r in rows]
    bs = sorted(base)
    wr = lambda v: (sum(1 for x in v if x > 0) / len(v)) if v else 0.0
    out = {"src": src, "hours": hrs, "n": len(rows), "base": sum(base), "base_day": sum(base) / hrs * 24 if hrs > 0 else 0,
           "base_wr": wr(base), "base_wo_top5": sum(bs[:-5]) if len(bs) > 5 else 0.0, "guards": {}}
    print(f"{src}  window {datetime.fromtimestamp(max(t0, lo) / 1e9, PKT):%m-%d %H:%M} -> {datetime.fromtimestamp(min(t1, hi) / 1e9, PKT):%m-%d %H:%M} PKT "
          f"({hrs:.1f} h) | trades {len(rows)} | realized {sum(base):+.3f} SOL ({out['base_day']:+.2f}/day) win {100 * wr(base):.0f}% | w/o top 5 {out['base_wo_top5']:+.3f}")
    ids = {g: {id(p) for p in blk[g]} for g in G}
    for g in G:
        b = [p["pnl"] for p in blk[g]]; s = sorted(b)
        kept = [r["pnl"] for r, p in zip(rows, pos) if id(p) not in ids[g]]
        ks = sorted(kept)
        o = {"blocked": len(b), "saved": -sum(b), "saved_day": -sum(b) / hrs * 24 if hrs > 0 else 0, "won_lost": [sum(1 for x in b if x > 0), sum(x for x in b if x > 0)],
             "losers": [sum(1 for x in b if x <= 0), sum(x for x in b if x <= 0)], "saved_wo_top5": -sum(s[5:]), "after": sum(kept), "after_wr": wr(kept),
             "after_wo_top5": sum(ks[:-5]) if len(ks) > 5 else 0.0, "big_losses_blocked": [sum(1 for x in b if x < -0.04), sum(x for x in b if x < -0.04)]}
        out["guards"][g] = o
        print(f"  {g:11s} blocked {o['blocked']:4d} (winners {o['won_lost'][0]} {o['won_lost'][1]:+.3f} | losers {o['losers'][0]} {o['losers'][1]:+.3f} | big losses {o['big_losses_blocked'][0]} {o['big_losses_blocked'][1]:+.3f})"
              f" saved {o['saved']:+.3f} SOL ({o['saved_day']:+.2f}/day), w/o its 5 best saves {o['saved_wo_top5']:+.3f} | after {o['after']:+.3f} win {100 * o['after_wr']:.0f}% w/o top5 {o['after_wo_top5']:+.3f}")
    # ESTIMATE: G2 at half size
    est = sum(((r["pnl"] + r["fixed"]) / 2 - r["fixed"]) - r["pnl"] for r in rows if "G2_CONC" in r["g"])
    out["E_CONC_HALF_estimate"] = est
    print(f"  E CONC_HALF (ESTIMATE: G2 trades at half size) change {est:+.3f} SOL ({est / hrs * 24 if hrs > 0 else 0:+.2f}/day)")
    if "--list" in sys.argv:
        for r in rows:
            if r["g"]:
                print(f"    {datetime.fromtimestamp(r['t'] / 1e9, PKT):%m-%d %H:%M:%S} {r['mint'][:8]} {r['kind']:5s} {r['pnl']:+.4f} {','.join(r['g'])} cr {r['cr_ledger']:+.3f} oth {r['sum_oth'] or 0:.1f} fresh {r['sum_fresh'] or 0:.1f} | {r['holders']}")
    if arg("--json"): json.dump({"summary": out, "rows": rows}, open(arg("--json"), "w"))
    if arg("--seed-out"):
        for t, c, v in pending: led[c].append((t, v))
        json.dump({c: [list(x) for x in v] for c, v in led.items()}, open(arg("--seed-out"), "w"))

if __name__ == "__main__":
    main()
