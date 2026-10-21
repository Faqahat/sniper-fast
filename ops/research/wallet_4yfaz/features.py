# READ-ONLY (host, no RPC): join 4yFAz's round trips (trades_rows.json) with their creates (creates.jsonl: create tx +
# the mint's signatures with block tx index up to his buy) -> landing (slot delta, tx position vs the creator's glued
# bundle, fill vs post-bundle price) and create-time features; tables by feature with his PnL; distribution vs our
# watched universe (filters3_rows.json). Writes feat_rows.json.
# usage: python3 features.py <trades_rows.json> <creates.jsonl> <tipmap.json> <filters3_rows.json> [detect_univ.json]
import sys, json, statistics, collections, time
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
T = {r["mint"]: r for r in json.load(open(sys.argv[1]))}
C = {}
for l in open(sys.argv[2]):
    r = json.loads(l)
    if r.get("create"): C[r["mint"]] = r
TM = json.load(open(sys.argv[3])); U = json.load(open(sys.argv[4]))["rows"]
DU = json.load(open(sys.argv[5])) if len(sys.argv) > 5 else {}


def tipc(dst):
    if not dst: return "none"
    if dst.startswith("moon"): return "lunar"
    if dst.startswith("noz"): return "nozomi"
    lab = TM.get(dst)
    if lab in ("jito", "nozomi"): return lab
    if lab: return "other tip svc"
    return "fee/other addr"


def host(uri):
    h = uri.split("/")[2] if "://" in uri else uri
    if "j7tracker" in h: return "j7tracker"
    if h == "ipfs.io": return "ipfs.io"
    if "uxento" in h: return "uxento"
    if "pinata" in h: return "pinata"
    return "other"


rows = []
for m, c in C.items():
    t = T.get(m)
    if not t: continue
    b0 = t["buy0"]; S = c["slot"]; cidx = c.get("tidx")
    sb = sorted([s for s in c["sigs_before"] if s[0] != c["sig"]], key=lambda s: (s[1], s[3] if s[3] is not None else 0))
    # glued: ok txs in S at consecutive indexes after the create
    ge = cidx; glued = 0
    okS = sorted([s for s in sb if s[1] == S and not s[2] and s[3] is not None], key=lambda s: s[3])
    for s in okS:
        if s[3] == ge + 1: glued += 1; ge += 1
        else: break
    ahead_ok = [s for s in sb if not s[2] and (s[1], s[3] or 0) < (b0["slot"], b0.get("tidx") or 10**6)]
    n_out = len(ahead_ok) - glued
    cm = [x for x in c["trades"] if x["mint"] == m]
    dev = sum(x["sol"] for x in cm if x["buy"]) / 1e9
    floor_px = cm[-1]["vsol"] / cm[-1]["vtok"] if cm else 30e9 / 1.073e15
    pre_px = (b0["vsol"] - b0["sol"] * 1e9) / (b0["vtok"] + b0["tok"])
    fill_px = b0["sol"] * 1e9 / b0["tok"]
    payer = c["payer"]; signers = set(c["signers"])
    tr = [x for x in c["transfers"] if x[0] == payer and x[1] not in signers]
    big = max(tr, key=lambda x: x[2]) if tr else None
    u = DU.get(m, {})
    rows.append(dict(mint=m, bt=t["bt"], S=S, dslot=b0["slot"] - S, cidx=cidx, b_tidx=b0.get("tidx"),
                     after_bundle=(b0["tidx"] - ge) if (b0["slot"] == S and b0.get("tidx") is not None and ge is not None) else None,
                     glued=glued, n_out_ahead=n_out, n_failed_before=sum(1 for s in sb if s[2]),
                     dev=dev, gsol_est=(pre_px / floor_px) if n_out == 0 else None,
                     pre_vs_floor=pre_px / floor_px, fill_vs_floor=fill_px / floor_px, fill_vs_pre=fill_px / pre_px,
                     vsol_pre=(b0["vsol"] - b0["sol"] * 1e9) / 1e9, size=t["sol_in"], pnl=t["pnl"], ret=t["ret"], hold_s=t["hold_s"], n_sells=t["n_sells"],
                     disc=c["create"]["disc"], name=c["create"]["name"], sym=c["create"]["sym"], uri=c["create"]["uri"], host=host(c["create"]["uri"]),
                     creator=c["create"]["creator"], payer=payer, create_cul=c["cul"], create_cup=c["cup"], create_nkeys=c["nkeys"], create_nsig=len(c["signers"]),
                     create_progs=[p[:6] for p in c["progs"]], tip_to=big[1] if big else None, tip_lam=big[2] if big else 0, tipc=tipc(big[1] if big else None),
                     create_fee=c["fee"], verdict=u.get("verdict"), buy_routes=b0["routes"], buy_cup=b0["cup"], buy_cul=b0["cul"], buy_fee=b0["txfee"], buy_tip=b0["tip"],
                     buy_prog=b0["prog"]))
json.dump(rows, open("feat_rows.json", "w"))
print(f"joined {len(rows)} of {len(T)} trades")


def tab(title, key, rs=rows):
    print(f"\n{title}")
    print("| value | n | share | his PnL | per trade | median | win |")
    print("|---|---|---|---|---|---|---|")
    g = collections.defaultdict(list)
    for r in rs: g[key(r)].append(r["pnl"])
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
        print(f"| {k} | {len(v)} | {len(v)/len(rs):.0%} | {sum(v):+.2f} | {statistics.mean(v):+.3f} | {statistics.median(v):+.3f} | {sum(x>0 for x in v)/len(v):.0%} |")


tab("Landing: slot delta (buy slot - create slot)", lambda r: r["dslot"])
tab("Outside (non-bundle) successful buys/sells ahead of him", lambda r: min(r["n_out_ahead"], 3))
tab("Creator glued bundle txs (consecutive after create)", lambda r: min(r["glued"], 4))
ab = [r["after_bundle"] for r in rows if r["after_bundle"] is not None]
if ab: print("\ntx index after glued bundle (same slot, incl. votes/other txs): median", statistics.median(ab), "p25", sorted(ab)[len(ab)//4], "p75", sorted(ab)[3*len(ab)//4], " ==1 (immediately behind):", sum(1 for x in ab if x == 1), "of", len(ab))
f = [r["fill_vs_floor"] for r in rows]; p = [r["pre_vs_floor"] for r in rows]
print("fill vs post-dev floor: median %.3f p25 %.3f p75 %.3f; price before his buy vs floor median %.3f" % (statistics.median(f), sorted(f)[len(f)//4], sorted(f)[3*len(f)//4], statistics.median(p)))
nb = [r for r in rows if r["n_out_ahead"] == 0]
print("when first outsider: price before him vs floor (=bundle push) median %.3f; his fill vs price before him median %.3f" % (statistics.median([r["pre_vs_floor"] for r in nb]), statistics.median([r["fill_vs_pre"] for r in nb])))
bk = lambda x, cuts: next((f"<{c}" for c in cuts if x < c), f">={cuts[-1]}")
tab("Dev buy SOL (create tx)", lambda r: bk(r["dev"], [0.01, 0.5, 1, 2, 3, 5, 8]))
tab("Bundle push = price before his buy / post-dev floor (no outsiders ahead only)", lambda r: bk(r["pre_vs_floor"], [1.01, 1.1, 1.25, 1.5, 2]), nb)
tab("Create tip destination class", lambda r: r["tipc"])
tab("Metadata host", lambda r: r["host"])
tab("Create kind (disc)", lambda r: {"d6904cec5f8b31b4": "create_v2", "181ec828051c0777": "create"}.get(r["disc"], r["disc"]))
tab("Engine verdict (where our logs cover it)", lambda r: r["verdict"] or "not in our logs")
tab("Size SOL", lambda r: bk(r["size"], [1, 1.5, 2, 2.5, 3, 4]))
tab("Buy route (tip account on landed tx)", lambda r: ",".join(r["buy_routes"]) or "no tip (prio only)")
tab("Creator cu price (uL)", lambda r: bk(r["create_cup"] or 0, [1, 100000, 1000000, 10000000]))
cc = collections.Counter(r["creator"] for r in rows)
print("\nrepeat creators among his picks:", sum(1 for k, v in cc.items() if v > 1), "creators with >1 pick, covering", sum(v for v in cc.values() if v > 1), "picks; top:", [(k[:6], v) for k, v in cc.most_common(8)])
pc = collections.Counter(r["payer"] for r in rows)
# size vs creator: does a creator always get the same size?
by_c = collections.defaultdict(list)
for r in rows: by_c[r["creator"]].append(round(r["size"], 2))
print("sizes by repeat creator:", {k[:6]: v for k, v in by_c.items() if len(v) > 1})
# universe comparison
UU = [u for u in U]
uc = lambda k: collections.Counter(k(u) for u in UU)
print("\nUNIVERSE (our watched launches A-E, n=%d) vs HIS PICKS (n=%d) - shares" % (len(UU), len(rows)))
for lab, fu, fh in (("tip class", lambda u: u["tipc"], lambda r: r["tipc"]), ("host", lambda u: u["host"], lambda r: r["host"]),
                    ("dev SOL", lambda u: bk(u["dev"], [0.01, 0.5, 1, 2, 3, 5, 8]), lambda r: bk(r["dev"], [0.01, 0.5, 1, 2, 3, 5, 8])),
                    ("glued txs", lambda u: min(u["glued"], 4), lambda r: min(r["glued"], 4))):
    a = uc(fu); b = collections.Counter(fh(r) for r in rows)
    print(f"  {lab}: " + "; ".join(f"{k}: univ {a[k]/len(UU):.0%} his {b[k]/len(rows):.0%}" for k in sorted(set(a) | set(b), key=str)))
