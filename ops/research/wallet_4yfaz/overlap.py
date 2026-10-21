# READ-ONLY (host, no RPC): which of our watched launches (FILTERS*.md rows, groups A-E; block recordings S..S+2) did 4yFAz
# trade, where did he sit vs the creator's glued bundle, and how did those launches do on our landing model (p2).
# usage: python3 overlap.py <filters3_rows.json> <rec dir> [<rec dir> ...] > overlap.txt ; writes overlap_rows.json
import sys, os, json, statistics, collections
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
rows = json.load(open(sys.argv[1]))["rows"]; RECS = sys.argv[2:]
lun = lambda r: r["tipc"] == "lunar"
early = lambda r: r["create_ms"] is not None and r["create_ms"] <= 150
R2 = lambda r: lun(r) and 3 <= r["gsol"] <= 5 and early(r)
out = []
for r in rows:
    rec = None
    for d in RECS:
        p = os.path.join(d, r["mint"] + ".json")
        if os.path.exists(p): rec = json.load(open(p)); break
    if not rec: continue
    tr = rec["trades"]; ge = rec["glued_end"]; S = rec["S"]
    his = [t for t in tr if t["user"] == W]
    hb = [t for t in his if t["buy"]]
    o = dict(mint=r["mint"], grp=r["grp"], S=S, r2=R2(r), early=early(r), tipc=r["tipc"], gsol=r["gsol"], glued=r["glued"], dev=r["dev"],
             host=r["host"], creator=r["creator"], p2=r["p2"], pp2=r["pp2"], refused=r["refused"], mkt2=r.get("mkt2"), cls=r["cls"], his=bool(hb))
    if hb:
        b = hb[0]
        # outside buys (not his) after the glued bundle and before his first buy, same block order
        ahead = [t for t in tr if t["buy"] and (t["slot"], t["idx"]) < (b["slot"], b["idx"]) and not (t["slot"] == S and t["idx"] < ge) and t["user"] != W]
        post_px = None
        gl = [t for t in tr if t["slot"] == S and t["idx"] < ge]
        if gl: post_px = gl[-1]["vsol"] / gl[-1]["vtok"]
        pre_v, pre_t = b["vsol"] - b["sol"], b["vtok"] + b["tok"]
        sells = [t for t in his if not t["buy"]]
        o.update(h_dslot=b["slot"] - S, h_idx=b["idx"], h_after_bundle=(b["idx"] - ge) if b["slot"] == S else None, h_ahead_n=len(ahead),
                 h_ahead_sol=sum(t["sol"] for t in ahead) / 1e9, h_sol=sum(t["sol"] for t in hb) / 1e9, h_nbuys=len(hb),
                 h_px_pre=(pre_v / pre_t) / post_px if post_px else None, h_fill=((sum(t["sol"] for t in hb) / sum(t["tok"] for t in hb)) / post_px) if post_px else None,
                 h_sells_in_rec=len(sells), h_sell_sol=sum(t["sol"] for t in sells) / 1e9)
    out.append(o)
json.dump(out, open("overlap_rows.json", "w"))
print("rows with recording", len(out), "of", len(rows))
for g in "ABCDE":
    xs = [o for o in out if o["grp"] == g]; h = [o for o in xs if o["his"]]; r2 = [o for o in xs if o["r2"]]; r2h = [o for o in r2 if o["his"]]
    print(f"grp {g}: watched {len(xs)}, he bought {len(h)} ({len(h)/max(1,len(xs)):.0%}); rule#2 {len(r2)}, he bought {len(r2h)}")
H = [o for o in out if o["his"]]; N = [o for o in out if not o["his"]]
f = lambda xs, k: statistics.mean([x[k] for x in xs]) if xs else float("nan")
print(f"\nour model p2 on launches he bought: n={len(H)} mean {f(H,'p2'):+.4f} sum {sum(x['p2'] for x in H):+.2f}; not bought n={len(N)} mean {f(N,'p2'):+.4f}")
for lab, sel in [("early<=150", lambda o: o["early"]), ("rule#2", lambda o: o["r2"]), ("no bundle", lambda o: o["glued"] == 0), ("bundle>0", lambda o: o["glued"] > 0)]:
    a = [o for o in H if sel(o)]; b = [o for o in N if sel(o)]
    print(f"  {lab:12} he bought n={len(a)} p2 {f(a,'p2'):+.4f} mkt2 {f([x for x in a if x['mkt2']],'mkt2'):.3f} | skipped n={len(b)} p2 {f(b,'p2'):+.4f} mkt2 {f([x for x in b if x['mkt2']],'mkt2'):.3f}")
print("\nhis landing on our watched launches: dslot", collections.Counter(o["h_dslot"] for o in H))
print("  txs after glued bundle (same slot):", sorted(o["h_after_bundle"] for o in H if o["h_after_bundle"] is not None))
print("  outside buys ahead of him:", collections.Counter(o["h_ahead_n"] for o in H).most_common())
print("  his fill (x post-bundle):", sorted(round(o["h_fill"], 3) for o in H if o["h_fill"]))
print("  his size SOL:", sorted(round(o["h_sol"], 2) for o in H))
print("\nrule #2 launches he bought:")
for o in H:
    if o["r2"]: print(f"  {o['grp']} {o['mint'][:8]} gsol {o['gsol']:.2f} dev {o['dev']:.2f} dslot {o['h_dslot']} after_bundle {o['h_after_bundle']} ahead {o['h_ahead_n']} size {o['h_sol']:.2f} fill {o['h_fill']} our p2 {o['p2']:+.3f}")
print("\nby tip class/host/bundle among watched early launches: share he bought")
for k in ("tipc", "host", "cls"):
    c = collections.Counter(o[k] for o in out if o["early"]); ch = collections.Counter(o[k] for o in H if o["early"])
    print(" ", k, {x: f"{ch[x]}/{n}" for x, n in c.most_common()})
bb = lambda g: "0" if g == 0 else ("<2" if g < 2 else ("2-3" if g < 3 else ("3-5" if g <= 5 else ">5")))
c = collections.Counter(bb(o["gsol"]) for o in out if o["early"]); ch = collections.Counter(bb(o["gsol"]) for o in H if o["early"])
print("  bundle SOL", {x: f"{ch[x]}/{n}" for x, n in c.most_common()})
