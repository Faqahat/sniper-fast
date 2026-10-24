#!/usr/bin/env python3
"""verify2 / v4: sensitivity of the corrected replay (repaired tape + absorbed-aware placement) and fat tails.
Writes work/v4_sens.json and prints tables."""
import sys, os, json, gzip, collections, statistics, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V

P = V.load_picks(); L = V.load_launches(P); D, O = V.load_scores(P); X = V.load_x1()
SLIP, kinds = V.load_slip(); PRO, SNIPER = V.load_wallet_sets()
ENG = json.load(open(os.path.join(V.WORK, "a6_engine.json")))
CLAIM = {r["m"]: r for r in json.load(open("/home/moiz/sniper/ops/overnight/core/final2_picks_v3_become_B0.5_tu.json"))}
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
lo, hi = min(slots), max(slots); EMPTY = {s for s in range(lo, hi + 1) if slots.get(s, 0) == 0}
PKT = datetime.timezone(datetime.timedelta(hours=5))
DEGRADED = {m for m in P if 460172456 - 60 <= L[m]["slot"] <= 460175266}
LAGGED = {m for m in P if D[m]["t_scored"] - D[m]["t"] > 1.0}
UNK = {m for m in P if D[m].get("glued_unknown") not in ("0", 0, None) or D[m].get("glued_closed") != "true"}
VARS = dict(slip=("S", None), proafter_slip=("S", "PRO"), nosnip=(None, "SNP"), nosnip_slip=("S", "SNP"), base=(None, None))
def dset(k): return None if k is None else (PRO if k == "PRO" else (SNIPER | PRO))
MINTS = {}; PLACE = {}
for m in P:
    M = V.Mint(m, L[m], X.get(m, []), repair=True, empty_slots=EMPTY)
    outs = V.parse_outs(O[m]["outs"]); seen, miss, how = V.match_anchors(M, outs); ab = V.absorbed_units(M, ENG.get(m), seen)
    MINTS[m] = M
    for Lm in (75, 45, 30):
        PLACE[(m, Lm)] = V.place2(M, seen, Lm, "opt", ab)
def run(Lm, var, subset=None, **kw):
    sk, dk = VARS[var]; out = {}
    for m in (subset or P):
        o = V.replay(MINTS[m], PLACE[(m, Lm)], slip=SLIP if sk else None, drop_buy=dset(dk), **kw)
        if o.get("fill") is None: continue
        out[m] = o
    return out
def summ(res):
    v = list(res.values()); f = [x for x in v if x["fill"]]; p = sorted(x["pnl"] for x in f)
    tot = sum(x["pnl"] for x in v)
    return dict(total=round(tot, 3), fills=len(f), n=len(v), med=round(statistics.median(p), 4) if p else None, win=sum(1 for x in p if x > 0),
                wo_top5=round(tot - sum(p[-5:]), 3), top5=round(sum(p[-5:]), 3))
S = {}
claim235 = [m for m in P if m in CLAIM]
print("corrected replay (repaired tape, absorbed-aware placement), claim's 235 picks, 0.5 SOL, today's costs")
for Lm in (75, 45, 30):
    for var in ("slip", "proafter_slip", "nosnip", "nosnip_slip"):
        r = run(Lm, var, claim235); s = summ(r); S[f"{Lm}|{var}|t8"] = s
        print(f"  L{Lm} {var:14s} total {s['total']:+.3f} fills {s['fills']}/{s['n']} median {s['med']:+.4f} win {s['win']}/{s['fills']} w/o top5 {s['wo_top5']:+.3f} (top5 {s['top5']:+.3f})")
print("\nhold-time sensitivity (slip variant, claim's 235): total SOL")
for Lm in (75, 45):
    row = []
    for h in (1, 2, 3, 5, 6, 7, 8, 9, 10, 12, 15, 20):
        s = summ(run(Lm, "slip", claim235, hold_s=float(h))); S[f"{Lm}|slip|t{h}"] = s; row.append(f"{h}s {s['total']:+.2f}")
    print(f"  L{Lm}: " + " | ".join(row))
    row = []
    for h in (5, 6, 7, 8, 9, 10, 12):
        s = summ(run(Lm, "proafter_slip", claim235, hold_s=float(h))); row.append(f"{h}s {s['total']:+.2f}")
    print(f"  L{Lm} proafter_slip: " + " | ".join(row))
print("\nother sensitivities (slip, t8, claim's 235)")
for Lm in (75, 45):
    base = summ(run(Lm, "slip", claim235))["total"]
    a = summ(run(Lm, "slip", claim235, buy_slot_mode="next"))["total"]
    b = summ(run(Lm, "slip", claim235, sell_cost=0.01))["total"]
    c = summ(run(Lm, "slip", claim235, fill_pen=0.0))["total"]
    d = summ(run(Lm, "slip", claim235, fill_pen=0.03))["total"]
    e = summ(run(Lm, "slip", claim235, over=0.047, fail_cost=0.0105))["total"]     # Run 2's real settings (~0.0235/buy, 0.0105/fail)
    f = summ(run(Lm, "slip", [m for m in claim235 if m not in DEGRADED]))["total"]
    g = summ(run(Lm, "slip", [m for m in claim235 if m not in LAGGED]))["total"]
    h = summ(run(Lm, "slip", [m for m in claim235 if m not in UNK]))["total"]
    i = summ(run(Lm, "slip", claim235, over=0.012, fail_cost=0.003))["total"]
    print(f"  L{Lm}: base {base:+.3f} | buy slot = next trade's {a:+.3f} | sell cost 0.01 {b:+.3f} | fill pen 0 {c:+.3f} / 3% {d:+.3f} | Run-2 fees {e:+.3f} | CW-style fees {i:+.3f}"
          f" | w/o degraded-collector picks ({len(DEGRADED & set(claim235))}) {f:+.3f} | w/o late-scored ({len(LAGGED & set(claim235))}) {g:+.3f} | w/o glued-unknown ({len(UNK & set(claim235))}) {h:+.3f}")
# halves and hours
print("\nby time (slip, t8, claim's 235)")
for Lm in (75, 45):
    r = run(Lm, "slip", claim235); bts = sorted(L[m]["bt"] for m in claim235); mid = bts[0] + (bts[-1] - bts[0]) / 2
    h1 = sum(o["pnl"] for m, o in r.items() if L[m]["bt"] < mid); h2 = sum(o["pnl"] for m, o in r.items() if L[m]["bt"] >= mid)
    byh = collections.defaultdict(float)
    for m, o in r.items(): byh[datetime.datetime.fromtimestamp(L[m]["bt"], PKT).strftime("%H")] += o["pnl"]
    print(f"  L{Lm}: halves {h1:+.3f} / {h2:+.3f} | by PKT hour: " + " ".join(f"{k}:{v:+.2f}" for k, v in sorted(byh.items(), key=lambda kv: (int(kv[0]) + 12) % 24)))
# fat tails at 75 ms
print("\ntop 10 winners / losers at 75 ms (slip, t8, all 238)")
r = run(75, "slip"); rp = run(75, "proafter_slip"); rn = run(75, "nosnip")
fills = sorted([(o["pnl"], m) for m, o in r.items() if o["fill"]], reverse=True)
TT = dict(winners=[], losers=[])
for tag, rows in (("winners", fills[:10]), ("losers", fills[-10:][::-1])):
    print(f"  -- {tag}")
    for pnl, m in rows:
        o = r[m]; c = CLAIM.get(m, {}).get("75", {}).get("slip")
        cl = ("%+.3f" % c["pnl"]["t8"]) if c and c.get("fill") else ("fail" if c else "n/a")
        row = dict(m=m, name=L[m].get("name"), created=datetime.datetime.fromtimestamp(L[m]["bt"], PKT).strftime("%m-%d %H:%M:%S"), pnl=round(pnl, 4),
                   pnl_proafter=round(rp[m]["pnl"], 4), pnl_nosnip=round(rn[m]["pnl"], 4), claim=cl, mult=round(o["mult"], 3), n_after=o["n_after"],
                   ins_sig=o["ins_sig"], last_sig=o["last_sig"], create_sig=L[m]["sig"], degraded=m in DEGRADED, gaps=MINTS[m].n_gap)
        TT[tag].append(row)
        print(f"   {pnl:+.3f} (pros-removed {rp[m]['pnl']:+.3f}, snipers-removed {rn[m]['pnl']:+.3f}; claim {cl}) x{o['mult']:.2f} {L[m].get('name','')[:22]:22s} {row['created']} "
              f"gmgn.ai/sol/token/{m} | buy after solscan.io/tx/{o['ins_sig']} | sell before last solscan.io/tx/{o['last_sig']}{' DEGRADED-DATA' if m in DEGRADED else ''}")
S["tails"] = TT
S["sets"] = dict(degraded=sorted(DEGRADED), lagged=sorted(LAGGED), unk=sorted(UNK))
json.dump(S, open(os.path.join(V.WORK, "v4_sens.json"), "w"), indent=1)
