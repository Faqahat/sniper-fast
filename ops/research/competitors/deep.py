# READ-ONLY (host, no RPC): deep dive on one competitor wallet from comp_rows.json: activity by hour, size tiers, exits,
# landing, fees/routes, selection inside our watched launches (pick rate + its PnL by create-time feature), pre/post Alpenglow.
# usage: python3 -I deep.py <wallet prefix> <comp_rows.json> <launches.json> <filters3_rows.json> [<cand.json>]
import sys, json, statistics, collections, time
WP, CRJ, LJ, F3 = sys.argv[1:5]
AG = 459653000
CR = [r for r in json.load(open(CRJ)) if r["wallet"].startswith(WP)]
W = CR[0]["wallet"]
LA = json.load(open(LJ)); F = {r["mint"]: r for r in json.load(open(F3))["rows"]}
med = lambda xs: statistics.median(xs) if xs else float("nan")
mean = lambda xs: statistics.mean(xs) if xs else float("nan")
cl = [r for r in CR if r["closed"]]


def line(lab, xs):
    if not xs: return f"  {lab:28} n 0"
    p = [r["pnl"] for r in xs]
    return (f"  {lab:28} n {len(xs):4}  PnL {sum(p):+7.2f}  mean {mean(p):+.4f}  med {med(p):+.4f}  win {sum(x>0 for x in p)/len(p):4.0%}  "
            f"ret {sum(p)/max(1e-9, sum(r['sol_in'] for r in xs)):+6.2%}  size {med([r['sol_in'] for r in xs]):.2f}")


print(f"=== {W}  trades {len(CR)} closed {len(cl)}  span {time.strftime('%m-%d %H:%M', time.gmtime(min(r['bt'] for r in CR)))} .. {time.strftime('%m-%d %H:%M', time.gmtime(max(r['bt'] for r in CR)))} UTC")
print(line("all closed", cl))
print(line("pre-Alpenglow", [r for r in cl if r["slot"] < AG]))
print(line("post-Alpenglow", [r for r in cl if r["slot"] >= AG]))
print("\nby UTC hour (n / PnL):", " ".join(f"{h}:{len(v)}/{sum(r['pnl'] for r in v):+.2f}" for h, v in sorted(collections.defaultdict(list, {}).items())) or "", end="")
hr = collections.defaultdict(list)
for r in cl: hr[time.strftime("%d %H", time.gmtime(r["bt"]))].append(r)
print(" ".join(f"{h}h:{len(v)}/{sum(r['pnl'] for r in v):+.2f}" for h, v in sorted(hr.items())))

print("\nsize tiers:")
sz = collections.Counter(round(r["sol_in"], 2) for r in CR)
print("  most common sizes (SOL in incl. pump fee):", sz.most_common(10))
for a, b in ((0, 0.75), (0.75, 1.25), (1.25, 1.75), (1.75, 2.5), (2.5, 4), (4, 99)):
    print(line(f"size {a}-{b}", [r for r in cl if a <= r["sol_in"] < b]))

print("\nexits:")
hs = [r["hold_s"] for r in cl if r["hold_s"] is not None]; hsl = [r["hold_slots"] for r in cl if r["hold_slots"] is not None]
print(f"  hold s: median {med(hs)}, p25 {sorted(hs)[len(hs)//4]}, p75 {sorted(hs)[3*len(hs)//4]}, p90 {sorted(hs)[int(.9*len(hs))]}; slots median {med(hsl)}")
print("  hold-time histogram (s):", sorted(collections.Counter(min(h, 60) // 2 * 2 for h in hs).items()))
print("  first sell slots after buy:", sorted(collections.Counter(min(r["first_sell_slots"], 50) for r in cl).items())[:25])
print("  sells per trade:", sorted(collections.Counter(r["n_sells"] for r in cl).items()))
print("  first leg fraction:", sorted(collections.Counter(round(r["first_leg"], 1) for r in cl if r["first_leg"] is not None).items()))
for lab, sel in (("single sell", lambda r: r["n_sells"] == 1), ("ladder 2+", lambda r: r["n_sells"] >= 2)):
    print(line(lab, [r for r in cl if sel(r)]))
for a, b in ((0, 1), (1, 2), (2, 4), (4, 8), (8, 16), (16, 40), (40, 10 ** 6)):
    print(line(f"hold {a}-{b} s", [r for r in cl if r["hold_s"] is not None and a <= r["hold_s"] < b]))

print("\nlanding (create slot known from our logs/recordings):")
k = [r for r in CR if r["dslot"] is not None]
print(f"  n {len(k)}; slot delta: {sorted(collections.Counter(r['dslot'] for r in k).items())}")
for d in (0, 1, 2):
    print(line(f"dslot {d}", [r for r in cl if r["dslot"] == d]))
wk = [r for r in CR if r["watched"]]
print(f"  on our watched launches (recordings): n {len(wk)}; outsider rank med {med([r['rank'] for r in wk if r['rank']])}; "
      f"first outsider {sum(r['rank']==1 for r in wk)}; same-slot tx gap after bundle med {med([r['after_bundle'] for r in wk if r['after_bundle'] is not None])}; "
      f"fill vs post-bundle med {med([r['fill'] for r in wk if r['fill']]):.3f}; our feed saw it at med {med([r['feed_ms'] for r in wk if r['feed_ms'] is not None])} ms "
      f"(n {sum(r['feed_ms'] is not None for r in wk)}; p25 {sorted([r['feed_ms'] for r in wk if r['feed_ms'] is not None] or [0])[len([r for r in wk if r['feed_ms'] is not None])//4]})")
print("  curve SOL ahead of its buy (dev+bundle+others), median:", round(med([r["curve_sol_before"] for r in CR]), 2))

print("\nfees / routes:")
print(f"  buy fee (base+prio) med {med([r['buy_fee'] for r in CR]):.5f}, tip med {med([r['buy_tip'] for r in CR]):.5f}, total med {med([r['buy_fee']+r['buy_tip'] for r in CR]):.5f} "
      f"({med([(r['buy_fee']+r['buy_tip'])/r['sol_in'] for r in CR]):.2%} of size); sell cost med {med([r['sell_cost'] for r in cl]):.5f}")
print("  buy routes:", collections.Counter(x for r in CR for x in (r["buy_routes"] or ["none"])).most_common(10))
print("  sell routes:", collections.Counter(x for r in cl for x in (r["sell_routes"] or ["none"])).most_common(6))
print("  durable nonce on buy:", sum(bool(r["buy_nonce"]) for r in CR), "/", len(CR), "; tx version:", collections.Counter(str(r["buy_ver"]) for r in CR).most_common(), "; CU limit:", collections.Counter(r["buy_cul"] for r in CR).most_common(4), "; CU used med", med([r["buy_cu"] for r in CR if r["buy_cu"]]))
print("  buy programs:", collections.Counter(tuple(r["buy_progs"]) for r in CR).most_common(3))
for a, b in ((0, 1.25), (1.25, 2.5), (2.5, 99)):
    xs = [r for r in CR if a <= r["sol_in"] < b]
    if xs: print(f"    size {a}-{b}: fee+tip med {med([r['buy_fee']+r['buy_tip'] for r in xs]):.4f} p90 {sorted([r['buy_fee']+r['buy_tip'] for r in xs])[int(.9*len(xs))]:.4f}")

print("\nengine verdicts of its mints (our DETECT logs):", collections.Counter(r["verdict"] for r in CR).most_common())
print(line("on our watched launches", [r for r in cl if r["watched"]]))
print(line("on rule #2 launches", [r for r in cl if r["r2"]]))
print(line("on rule #2 w/o create-ms", [r for r in cl if r["r2nc"]]))
print(line("not watched", [r for r in cl if not r["watched"]]))

# selection inside our watched launches, only while the wallet was active (it traded something within +-20 min)
bts = sorted(r["bt"] for r in CR)
import bisect
def active(t):
    i = bisect.bisect_left(bts, t - 1200)
    return i < len(bts) and bts[i] <= t + 1200
av = [l for l in LA if l["bt"] and active(l["bt"])]
picked = {r["mint"]: r for r in CR}
print(f"\nselection: watched launches while it was active: {len(av)}; it bought {sum(l['mint'] in picked for l in av)} ({sum(l['mint'] in picked for l in av)/max(1,len(av)):.1%})")
def feat(l):
    f = F.get(l["mint"], {})
    return dict(tipc=f.get("tipc") or ("lunar" if l["moon"] else "non-lunar?"), host=f.get("host") or "?", client=f.get("cls") or "?",
                gsol="0" if not l["gsol"] else ("<2" if l["gsol"] < 2 else ("2-3" if l["gsol"] < 3 else ("3-5" if l["gsol"] <= 5 else ">5"))),
                glued=str(min(l["glued"] or 0, 4)), dev="<1" if (l["dev"] or 0) < 1 else ("1-2" if l["dev"] < 2 else ("2-4" if l["dev"] < 4 else ("4-6" if l["dev"] < 6 else "6+"))),
                cms="?" if l["cms"] is None else ("<=50" if l["cms"] <= 50 else ("<=150" if l["cms"] <= 150 else ">150")),
                r2="r2" if l["r2"] else "-", creator_prev="?" if f.get("c_prev_n") is None else ("0" if f["c_prev_n"] == 0 else ("1-3" if f["c_prev_n"] <= 3 else "4+")))
for key in ("r2", "tipc", "gsol", "glued", "dev", "cms", "host", "client", "creator_prev"):
    c = collections.Counter(feat(l)[key] for l in av); ch = collections.Counter(feat(l)[key] for l in av if l["mint"] in picked)
    pn = collections.defaultdict(list); p2 = collections.defaultdict(list)
    for l in av:
        if l["mint"] in picked and picked[l["mint"]]["closed"]: pn[feat(l)[key]].append(picked[l["mint"]]["pnl"])
        if l["p2"] is not None: p2[feat(l)[key]].append(l["p2"])
    print(f"  {key:12} " + " | ".join(f"{v}: {ch[v]}/{n} ({ch[v]/n:.0%}) pnl {sum(pn[v]):+.2f} our_p2/launch {mean(p2[v]):+.3f}" for v, n in c.most_common()))

print("\npre vs post Alpenglow (slot >= 459,653,000):")
for lab, xs in (("pre", [r for r in CR if r["slot"] < AG]), ("post", [r for r in CR if r["slot"] >= AG])):
    if not xs: print(f"  {lab}: n 0"); continue
    c = [r for r in xs if r["closed"]]; k = [r for r in xs if r["dslot"] is not None]
    hrs = (max(r["bt"] for r in xs) - min(r["bt"] for r in xs)) / 3600 or 1
    print(f"  {lab:5} n {len(xs):4} ({len(xs)/hrs:.1f}/h over {hrs:.1f} h)  PnL {sum(r['pnl'] for r in c):+.2f} ({sum(r['pnl'] for r in c)/hrs:+.2f}/h)  ret {sum(r['pnl'] for r in c)/max(1e-9,sum(r['sol_in'] for r in c)):+.2%}  "
          f"size {med([r['sol_in'] for r in xs]):.2f}  fee+tip {med([r['buy_fee']+r['buy_tip'] for r in xs]):.4f}  hold {med([r['hold_s'] for r in c if r['hold_s'] is not None])} s "
          f"({med([r['hold_slots'] for r in c if r['hold_slots'] is not None])} slots)  dslot0 {sum(r['dslot']==0 for r in k)}/{len(k)}  "
          f"win {sum(r['pnl']>0 for r in c)/max(1,len(c)):.0%}  watched {sum(r['watched'] for r in xs)}")
