#!/usr/bin/env python3
# READ-ONLY. Build /root/race/race_ds.jsonl: one row per SOL-quoted launch in /root/nob (random sample + 4yFAz picks)
# = create-time features (ds.jsonl + blk record) + RACE labels (race_lib.labels: outside buyers in S from the block,
# S+1..S+5 from s1.jsonl) + the shred-window signals (outside buys at non-vote offset d in S) + a price path for PnL.
# Also writes /root/race/pros.json: multi-creator sniper wallets (a glued tx from one of them is NOT creator bundle).
import json, sys, collections
sys.path.insert(0, "/root/race")
from race_lib import labels, path_pts, W, bad_events

D = "/root/nob/"
S1 = sys.argv[1:] or ["/root/race/s1.jsonl"]
SIZED = {"BuyExactSolIn", "BuyExactQuoteI"}
CAPK = {"Buy", "BuyV2", "BuyV3"}


def jl(p):
    out = []
    try:
        for l in open(p):
            try:
                out.append(json.loads(l))
            except Exception:
                pass
    except FileNotFoundError:
        pass
    return out


ds = {r["mint"]: r for r in jl(D + "ds.jsonl")}
blk = {}
for fn in ("blk_rand.jsonl", "blk_rand2.jsonl", "blk_his.jsonl"):
    for r in jl(D + fn):
        if "later" in r and r.get("mint"):
            blk.setdefault(r["mint"], r)
s1 = {}
for fn in S1:
    for r in jl(fn):
        if "sig_err" not in r and "rows" in r:
            s1[r["mint"]] = r
paths = {}
for fn in (D + "paths_rand.jsonl", D + "paths_his.jsonl", "/root/race/paths_extra.jsonl"):
    for r in jl(fn):
        if "sig_err" not in r and r.get("rows") is not None:
            paths[r["mint"]] = r
print("ds", len(ds), "blk", len(blk), "s1", len(s1), "paths", len(paths), file=sys.stderr)

# ---- pros: wallets buying (non-glued) launches of >=3 distinct creators, rarely glued themselves
nong, glu, crs = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
for m, b in blk.items():
    cset = {b["creator"], b["user"], b.get("payer")}
    for x in b.get("later") or []:
        if not x.get("ok"):
            continue
        for e in x["ev"]:
            if e[0] and e[1] not in cset:
                (glu if x.get("glued") else nong)[x["payer"]].add(m)
                crs[x["payer"]].add(b["creator"])
    for x in (s1.get(m) or {}).get("rows", []):
        if x.get("ev") and any(e[0] for e in x["ev"]) and x.get("payer") not in cset:
            nong[x["payer"]].add(m)
            crs[x["payer"]].add(b["creator"])
pros = {w for w in nong if len(nong[w]) >= 3 and len(crs[w]) >= 3 and len(glu[w]) <= len(nong[w]) / 2}
try:
    for l in open("/root/indep/buyers.jsonl"):
        x = json.loads(l)
        if x.get("cls") == "INDEP":
            pros.add(x["payer"])
except Exception:
    pass
pros.add(W)
json.dump(sorted(pros), open("/root/race/pros.json", "w"))
print("pros", len(pros), file=sys.stderr)


def build(m):
    f = ds[m]
    b = blk.get(m)
    s = s1.get(m)
    if f["quote"] or not b or not s:
        return None
    o = {k: f[k] for k in f if not k.startswith(("ret_", "adj_", "peak", "px"))}
    nnv, cnv = b.get("nnv") or 1000, b.get("cnv") or 0
    o["nnv"], o["cnv"], o["rem_nv"] = nnv, cnv, nnv - cnv
    ins = b.get("ins") or []
    bi = [x for x in ins if x.startswith("Buy")]
    o["dev_kind"] = "none" if not bi else ("sized" if any(x in SIZED for x in bi) else ("cap" if any(x in CAPK for x in bi) else "other"))
    o["dev_ix"] = "+".join(bi) or "none"
    o["n_signers"] = len(b.get("signers") or [])
    o["base"] = b.get("base") or (30e9 + f["dev_sol"] * 1e9)
    o["glued"] = b.get("glued", 0)
    o["gsol"] = (b.get("gsol") or 0) / 1e9
    o.update(labels(b, s, pros))
    o["bad_ev"] = bad_events(b, s)
    o["s1_capped"] = s.get("n_pick", 0) > len(s.get("rows", []))
    o["act"] = dict((str(k), v) for k, v in s.get("act", []))
    o["act_err"] = dict((str(k), v) for k, v in s.get("act_err", []))
    p = paths.get(m)
    o["path"], o["ms_per_tx"] = path_pts(b, s, (p or {}).get("rows"), f["slot"])
    o["has_path"] = p is not None
    o["sv"] = [(x["d"], x["ev"][-1][4]) for x in b.get("later") or [] if x.get("ok") and x["ev"]][:300]
    return o


rows = [r for r in (build(m) for m in ds) if r]
rows.sort(key=lambda r: r["slot"])
with open("/root/race/race_ds.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")
print("rows", len(rows), "rand", sum(r["in_rand"] for r in rows), "his", sum(r["his"] for r in rows), file=sys.stderr)
