# READ-ONLY (host, no RPC): find wallets that buy launches like ours in the create slot S or S+1, from every block
# recording we have (rec/ A-C, rec_dry1h, paper loop copies D/E/post-E). Joins filters3_rows.json (rule #2 flag, our
# modelled S+2 PnL) and the engines' RACE obs feed timelines (ms after the create when our feed saw each outside buy).
# usage: python3 -I discover.py <out_dir> <filters3_rows.json> <rec_dir> [<rec_dir> ...]   (logs via env LOGS=a.log:b.log)
# writes <out_dir>/launches.json (one row per mint, merged) and <out_dir>/cand.json (per-wallet stats); prints the ranking.
import sys, os, json, glob, statistics, collections, re
OUT, F3 = sys.argv[1], sys.argv[2]; RECS = sys.argv[3:]
OURS = ("FRZh63", "2g7rYv")
FAZ = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
AG = 459653000          # Alpenglow activation slot
rows = {r["mint"]: r for r in json.load(open(F3))["rows"]}

# ---- merge recordings: prefer the longest window per mint
L = {}
for d in RECS:
    for f in glob.glob(os.path.join(d, "*.json")):
        try: r = json.load(open(f))
        except Exception: continue
        if not isinstance(r, dict) or "S" not in r or "trades" not in r: continue
        m = r["mint"]
        if m not in L or (r.get("window_slots") or 0) > (L[m].get("window_slots") or 0): L[m] = r

# ---- feed timelines from engine logs: mint -> [(ms, sol, flag, w6)]
FEED = {}
for lf in [x for x in os.environ.get("LOGS", "").split(":") if x]:
    for line in open(lf, errors="replace"):
        if "RACE obs" not in line: continue
        m = re.search(r"mint=(\S+)", line); o = re.search(r"outs=(\S*)", line)
        if not m or not o: continue
        outs = []
        for it in o.group(1).split(","):
            p = it.split(":")
            if len(p) >= 4:
                try: outs.append((float(p[0]), float(p[1]), p[2], p[3]))
                except ValueError: pass
        FEED.setdefault(m.group(1), outs)

def r2_of(rec, row):
    if row is not None:
        return row["tipc"] == "lunar" and 3 <= row["gsol"] <= 5 and row["create_ms"] is not None and row["create_ms"] <= 150
    cms = rec.get("create_ms")
    return bool(rec.get("largest_moon")) and 3 <= (rec.get("gsol") or 0) <= 5 and cms is not None and cms <= 150

def r2_nocms(rec):
    return bool(rec.get("largest_moon")) and 3 <= (rec.get("gsol") or 0) <= 5

launches = []; W = collections.defaultdict(list)
for m, rec in L.items():
    S = rec["S"]; ge = rec.get("glued_end") or 0; tr = rec["trades"]
    row = rows.get(m)
    bm = set(rec.get("bundle_members") or []); cre = rec.get("creator")
    excl = bm | {cre, FAZ}
    # outside buys in S (after the glued bundle) and S+1, in block order
    outs = [t for t in sorted(tr, key=lambda t: (t["slot"], t["idx"])) if t["buy"] and t["slot"] in (S, S + 1)
            and not (t["slot"] == S and t["idx"] < ge)]
    first_out = None
    lrow = dict(mint=m, S=S, bt=rec.get("block_time"), creator=cre, gsol=rec.get("gsol"), glued=rec.get("glued"), dev=rec.get("dev"),
                moon=rec.get("largest_moon"), cms=rec.get("create_ms"), r2=r2_of(rec, row), r2nc=r2_nocms(rec), grp=row["grp"] if row else None,
                p2=row["p2"] if row else None, refused=row["refused"] if row else None, win=rec.get("window_slots"), post_ag=S >= AG,
                host=(row or {}).get("host"), tipc=(row or {}).get("tipc"), client=(row or {}).get("client"), fired=rec.get("fired"))
    launches.append(lrow)
    feed = FEED.get(m, [])
    rank = 0
    for t in outs:
        u, p = t["user"], t["payer"]
        if u in excl or p in excl or u.startswith(OURS) or p.startswith(OURS): continue
        rank += 1
        fms = [x[0] for x in feed if x[3] and (u.startswith(x[3]) or p.startswith(x[3]))]
        # the wallet's own sells inside the recording window
        sells = [x for x in tr if not x["buy"] and x["user"] == u]
        pre_v, pre_t = t["vsol"] - t["sol"], t["vtok"] + t["tok"]
        gl = [x for x in tr if x["slot"] == S and x["idx"] < ge]
        post_px = (gl[-1]["vsol"] / gl[-1]["vtok"]) if gl else None
        W[u].append(dict(mint=m, S=S, dslot=t["slot"] - S, idx=t["idx"], after_bundle=(t["idx"] - ge) if t["slot"] == S else None, rank=rank,
                         sol=t["sol"] / 1e9, payer=p, r2=lrow["r2"], r2nc=lrow["r2nc"], moon=lrow["moon"], gsol=lrow["gsol"], dev=lrow["dev"],
                         creator=cre, p2=lrow["p2"], refused=lrow["refused"], feed_ms=min(fms) if fms else None, post_ag=lrow["post_ag"],
                         fill=((t["sol"] / t["tok"]) / post_px) if post_px and t["tok"] else None,
                         px_pre=((pre_v / pre_t) / post_px) if post_px else None,
                         sold_in_win=sum(x["tok"] for x in sells) / t["tok"] if t["tok"] else None, win=lrow["win"], bt=lrow["bt"]))

json.dump(launches, open(os.path.join(OUT, "launches.json"), "w"))
NL = len(launches); NR2 = sum(l["r2"] for l in launches)
print(f"launches {NL} (rule#2 {NR2}, rule#2 w/o create-ms {sum(l['r2nc'] for l in launches)}, post-Alpenglow {sum(l['post_ag'] for l in launches)}), feed timelines {len(FEED)}")
cand = []
for u, xs in W.items():
    lane = [x for x in xs if 0.5 <= x["sol"] <= 3.0]
    q = lambda k, ys: statistics.median([y[k] for y in ys if y[k] is not None]) if any(y[k] is not None for y in ys) else None
    cand.append(dict(wallet=u, n=len(xs), n_lane=len(lane), n_creators=len({x["creator"] for x in xs}), n_r2=sum(x["r2"] for x in xs),
                     n_r2nc=sum(x["r2nc"] for x in xs), n_moon=sum(bool(x["moon"]) for x in xs), n_s=sum(x["dslot"] == 0 for x in xs),
                     n_post=sum(x["post_ag"] for x in xs), sol_med=q("sol", xs), sizes=sorted(round(x["sol"], 2) for x in xs),
                     rank_med=q("rank", xs), first=sum(x["rank"] == 1 for x in xs), feed_med=q("feed_ms", xs), n_feed=sum(x["feed_ms"] is not None for x in xs),
                     fill_med=q("fill", xs), p2_sum=sum(x["p2"] for x in xs if x["p2"] is not None), payers=collections.Counter(x["payer"] for x in xs).most_common(3),
                     sold_win=sum(1 for x in xs if (x["sold_in_win"] or 0) > 0.5), trades=xs))
cand.sort(key=lambda c: (-c["n_lane"], -c["n"]))
json.dump(cand, open(os.path.join(OUT, "cand.json"), "w"))
print(f"wallets with >=1 outside S/S+1 buy: {len(cand)}; with >=5: {sum(c['n']>=5 for c in cand)}; >=10: {sum(c['n']>=10 for c in cand)}")
print("\nrank wallet        n  lane cre  r2 r2nc moon  S%  post  size_med  rank_med first  feed_ms(n)  fill  sold<=S+2  our_p2_sum  payers")
for i, c in enumerate([c for c in cand if c["n"] >= 4][:60]):
    fm = f"{c['feed_med']:.0f}({c['n_feed']})" if c["feed_med"] is not None else "-"
    print(f"{i+1:3} {c['wallet'][:12]} {c['n']:3} {c['n_lane']:4} {c['n_creators']:3} {c['n_r2']:3} {c['n_r2nc']:4} {c['n_moon']:4} {c['n_s']/c['n']:4.0%} {c['n_post']:4}  {c['sol_med']:7.2f}  {c['rank_med']:7.1f} {c['first']:4}  {fm:>10}  {c['fill_med'] or 0:5.2f}  {c['sold_win']:4}  {c['p2_sum']:+8.2f}  "
          + " ".join(f"{p[:6]}x{n}" for p, n in c["payers"]))
