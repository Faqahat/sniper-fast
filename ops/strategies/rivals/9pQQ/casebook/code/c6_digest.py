#!/usr/bin/env python3
"""CASEBOOK step 6: compact readable digest of one token (for the analyst) from the ev table.
usage: c6_digest.py RUN MINT  -> prints; also saved to casebook/tapes/<run>/<mint>.digest.txt"""
import sys, json, gzip, datetime, statistics as st, collections, io
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
D = "/home/it/sniper-data/rivals/9pQQ/casebook"; COL = "/data/tapes/collect"
def pkt(bt): return (datetime.datetime.utcfromtimestamp(bt) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M:%S")
run, mint = sys.argv[1], sys.argv[2]
R = [json.loads(l) for l in gzip.open(f"{D}/tapes/{run}/{mint}.ev.jsonl.gz", "rt")]
out = io.StringIO()
def P(*a): print(*a, file=out)
meta = {}
for l in open(f"{COL}/{run}/enrich.jsonl"):
    if mint in l:
        d = json.loads(l)
        if d.get("mint") == mint: meta = d; break
mj = ((meta.get("meta") or {}).get("json") or {})
P(f"### {mint} ({run})  name={mj.get('name')!r} twitter={mj.get('twitter')} tg={mj.get('telegram')} web={mj.get('website')} creator_prior={len(meta.get('creator_prior_sigs') or [])}")
own = [r for r in R if r["own"]]
P(f"trades {len(R)}, outside {len(R)-len(own)}, own {len(own)}; active age {R[0]['age']}..{R[-1]['age']} slots; peak mc {max(r['mc'] for r in R):.0f}")
trips = []; b = None
for k, r in enumerate(R):
    if not r["own"]: continue
    if r["buy"]: b = (k, r)
    elif b: trips.append((b, (k, r))); b = None
def fmt(r, ref=None):
    ds = f"d{r['s']-ref['s']}/{r['i']-ref['i'] if r['s']==ref['s'] else r['i']}" if ref else ""
    return f"{'B' if r['buy'] else 'S'}{r['sol']:.3f} {r['u'][:5]} uc{r['ucnt']} {r['pr'] or 'pump'} t{r['tip']//1000}k cup{r['cup']//1000}k {ds}"
P("\n## trips")
tot = 0
for n, ((kb, b), (ks, s)) in enumerate(trips, 1):
    hold = [r for r in R[kb + 1:ks] if not r["own"]]
    hb = sum(r["sol"] for r in hold if r["buy"]); hs = sum(r["sol"] for r in hold if not r["buy"])
    rets = [r["ret"] for r in hold if r.get("ret") is not None] or [0]
    after = [r for r in R[ks + 1:] if r["s"] <= s["s"] + 150]
    a25 = [r for r in after if r["s"] <= s["s"] + 25]
    mv25 = (a25[-1]["mc"] / s["mc"] - 1) * 100 if a25 else 0; mv150 = (after[-1]["mc"] / s["mc"] - 1) * 100 if after else 0
    ret = (s["pre_mc"] / b["mc"] - 1) * 100 if s.get("pre_mc") else 0
    P(f"T{n} buy +{b['age']} {pkt(b['bt'])} mc {b['mc']:.1f} (pre {b['pre_mc']}) vs_exit {b['vs_exit']} since_sell {b['since_sell']} | trig[{b['trig_dslot']}] "
      f"nf10 {R[kb-1]['nf10'] if kb else ''} ch10 {R[kb-1]['ch10'] if kb else ''} ch50 {R[kb-1]['ch50'] if kb else ''} g_open {b['g_open']} lead {b['lead']}")
    pre = [r for r in R[max(0, kb - 8):kb] if not r["own"] and r["s"] >= b["s"] - 3]
    for r in pre: P("     <", fmt(r, b), f"fs{r['fail_slot']}/{r['fail_prev']} mc{r['mc']:.1f}")
    P(f"   hold {s['s']-b['s']} sl ({s['bt']-b['bt']} s): {len(hold)} outside trades, +{hb:.2f}/-{hs:.2f} SOL, ret hi {max(rets)} lo {min(rets)}; exit ret {ret:.1f}%  "
      f"after-sell mc 25sl {mv25:+.1f}% 150sl {mv150:+.1f}%")
    pre = [r for r in R[max(0, ks - 6):ks] if not r["own"] and r["s"] >= s["s"] - 3]
    for r in pre: P("     <", fmt(r, s), f"mc{r['mc']:.1f}")
    c3 = [r for r in R[:ks] if r["s"] <= s["s"] - 3]
    ch3 = (s["pre_mc"] / c3[-1]["mc"] - 1) * 100 if c3 and s.get("pre_mc") else 0
    era = "V3" if s["bt"] >= 1793388600 else "V2/1"
    P(f"   sell +{s['age']} {era} trig[{s['trig_dslot']}] since_ob {R[ks-1]['since_ob'] if ks else ''} peak_ret {max(rets)} dd_at_sell {R[ks-1].get('dd_peak')} ch3 {ch3:.1f}% hold_s {s['bt']-b['bt']}")
# flat-eligible decision moments
P("\n## flat moments (outside trades while flat, age>=8, >=2 slots after own sell): taken vs skipped")
E = [r for r in R if not r["own"] and not r["hold"] and r["age"] >= 8 and (r["since_sell"] is None or r["since_sell"] >= 2)]
tk = [r for r in E if r.get("trig") == "B"]; sk = [r for r in E if r.get("trig") != "B"]
P(f"eligible {len(E)}, taken {len(tk)} ({100*len(tk)/max(1,len(E)):.2f}%), failed-buy triggers {sum(1 for r in E if r.get('ftrig'))}")
def q(xs):
    xs = [x for x in xs if x is not None]
    if not xs: return "-"
    xs = sorted(xs); return f"{xs[len(xs)//4]:.3g}/{xs[len(xs)//2]:.3g}/{xs[3*len(xs)//4]:.3g}"
for f in ["sol", "nf10", "ns10", "ch10", "dd450", "ucnt", "since_sell", "vs_exit", "n75"]:
    P(f"  {f:10s} taken {q([r[f] for r in tk])}   skipped {q([r[f] for r in sk])}")
P(f"  side B share: taken {sum(r['buy'] for r in tk)}/{len(tk)}  skipped {sum(r['buy'] for r in sk)}/{len(sk)}")
pc = collections.Counter(r["pr"] or "pump" for r in sk); pt = collections.Counter(r["pr"] or "pump" for r in tk)
P("  progs taken", dict(pt.most_common(6)), " skipped", dict(pc.most_common(6)))
P("  biggest skipped flat triggers:")
for r in sorted(sk, key=lambda r: -r["sol"])[:10]:
    P(f"     +{r['age']} {pkt(r['bt'])[6:]} {fmt(r)} mc{r['mc']:.1f} ch10 {r['ch10']} since_sell {r['since_sell']} ntrips {r['ntrips']}")
# holding moments
H = [r for r in R if not r["own"] and r["hold"]]
P(f"\n## hold moments: {len(H)} outside trades while holding; sells {sum(1 for r in H if r.get('trig')=='S')}")
hs = [r for r in H if r.get("trig") == "S"]; hn = [r for r in H if r.get("trig") != "S"]
for f in ["sol", "ret", "dd_peak", "since_buy", "since_ob", "nf10"]:
    P(f"  {f:10s} sold-on {q([r.get(f) for r in hs])}   not {q([r.get(f) for r in hn])}")
P(f"  side B share: sold-on {sum(r['buy'] for r in hs)}/{len(hs)}  not {sum(r['buy'] for r in hn)}/{len(hn)}")
P("  biggest outside sells it held through:")
for r in sorted([r for r in hn if not r["buy"]], key=lambda r: -r["sol"])[:6]:
    P(f"     +{r['age']} {fmt(r)} ret {r['ret']} dd {r.get('dd_peak')} since_buy {r['since_buy']}")
# after last exit
if trips:
    ls = trips[-1][1][1]
    aft = [r for r in R if r["s"] > ls["s"]]
    P(f"\n## after last exit (+{ls['age']}): {len(aft)} more trades, last at +{aft[-1]['age'] if aft else '-'}; outside buys>=0.5 after: {sum(1 for r in aft if r['buy'] and r['sol']>=0.5)}; peak mc after {max([r['mc'] for r in aft] or [0]):.0f}")
txt = out.getvalue(); print(txt)
open(f"{D}/tapes/{run}/{mint}.digest.txt", "w").write(txt)
