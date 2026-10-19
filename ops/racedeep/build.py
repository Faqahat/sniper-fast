#!/usr/bin/env python3
# READ-ONLY. racedeep builder: one unified per-launch timeline for hist (race_ds + nob blk + s1), fwd run 1 and the night run.
# out: /root/racedeep/U.pkl  (list of dicts)
import sys, json, pickle, collections
sys.path.insert(0, "/root/race")
from race_lib import labels, W, bad_events, OURS
from hc_search import hostbad
from fwdrows import build

SLOT = 217.0
pros = frozenset(json.load(open("/root/race/pros.json")))


def tipsum(x):
    return sum(t[1] for t in (x.get("tips") or [])) / 1e9


def timeline(b, s, eng_path=None, hist_path=None):
    """trades: list of (t_ms, k_slot, pos, typ, sol, payer, cu, tip, vsol, his)
    typ: O outsider buy, I insider buy (creator/bundle/creator-side), X sell, E failed tx (S only)"""
    nnv, cnv = b.get("nnv") or 400, b.get("cnv") or 0
    mpt = SLOT / max(nnv, 1)
    rem = max(nnv - 1 - cnv, 0)
    tS = (rem + 1) * mpt
    creator, user = b["creator"], b["user"]
    cset = {creator, user, b.get("payer")} | set(b.get("signers") or []) | OURS
    broken = False
    glued_out = set()
    for x in b.get("later") or []:
        if x.get("glued"):
            if broken or x["payer"] in pros or x.get("his"):
                broken = True
                glued_out.add(x["sig"])
            else:
                cset.add(x["payer"])
                for e in x["ev"]:
                    cset.add(e[1])
    tr = []
    for x in b.get("later") or []:
        t = x["d"] * mpt
        if not x.get("ok"):
            tr.append((t, 0, x["d"], "E", 0.0, x.get("payer"), x.get("cu_price") or 0, tipsum(x), None, bool(x.get("his"))))
            continue
        if not x["ev"]:
            continue
        evb = [e for e in x["ev"] if e[0]]
        his = bool(x.get("his") or any(e[1] == W for e in x["ev"]))
        v = x["ev"][-1][4]
        if not evb:
            tr.append((t, 0, x["d"], "X", sum(e[2] for e in x["ev"]) / 1e9, x["payer"], x.get("cu_price") or 0, tipsum(x), v, his))
            continue
        ins = (x.get("glued") and x["sig"] not in glued_out) or x["payer"] in cset or {e[1] for e in evb} <= cset
        tr.append((t, 0, x["d"], "I" if ins else "O", sum(e[2] for e in evb) / 1e9, x["payer"], x.get("cu_price") or 0, tipsum(x), v, his))
    seq = collections.defaultdict(list)
    for x in (s or {}).get("rows", []):
        if "ev" in x:
            seq[x["d"]].append(x)
    for k in sorted(seq):
        rows = seq[k]
        for i, x in enumerate(rows):
            if not x["ev"]:
                continue
            t = tS + (k - 1) * SLOT + SLOT * i / max(len(rows), 1)
            evb = [e for e in x["ev"] if e[0]]
            his = x["payer"] == W or any(e[1] == W for e in x["ev"])
            v = x["ev"][-1][4]
            if not evb:
                tr.append((t, k, i, "X", sum(e[2] for e in x["ev"]) / 1e9, x["payer"], x.get("cu_price") or 0, tipsum(x), v, his))
                continue
            ins = x["payer"] in cset or {e[1] for e in evb} <= cset
            tr.append((t, k, i, "I" if ins else "O", sum(e[2] for e in evb) / 1e9, x["payer"], x.get("cu_price") or 0, tipsum(x), v, his))
    tr.sort(key=lambda z: z[0])
    # price path (t, vsol): every trade, then tail
    path = [(0.0, b.get("base"))] + [(z[0], z[8]) for z in tr if z[8]]
    last = max(path[-1][0], tS + 5 * SLOT)
    capped = (s or {}).get("n_pick", 0) > len((s or {}).get("rows", []))
    if eng_path:
        for ms, rb in eng_path:
            t = 200.0 + ms
            if t > last:
                path.append((t, b["base"] * max(rb, 1e-6) ** 0.5))
    elif hist_path:
        thr = 6 * SLOT if (s or {}).get("rows") else SLOT
        for t, v in hist_path:
            if t >= thr:   # nob later path rows: slot-based (d*217+216) -> re-time to after-create
                path.append((t - SLOT + tS, v))
    path.sort(key=lambda z: z[0])
    return dict(mpt=mpt, rem=rem, tS=tS, tr=tr, path=path, capped=capped, base=b.get("base"), nnv=nnv, cnv=cnv,
                n_err_S=sum(1 for z in tr if z[3] == "E"), act_err=(s or {}).get("act_err"), act=(s or {}).get("act"))


U = []
# ---------------- hist
R = [json.loads(l) for l in open("/root/race/race_ds.jsonl")]
H = [r for r in R if not r["quote"] and not r["mayhem"] and not hostbad(r.get("uri_host")) and 0.5 <= r["dev_sol"] <= 8 and r["has_path"] and not r.get("bad_ev")]
need = {r["mint"] for r in H}
blk = {}
for fn in ("/root/nob/blk_rand.jsonl", "/root/nob/blk_rand2.jsonl", "/root/nob/blk_his.jsonl"):
    for l in open(fn):
        try:
            x = json.loads(l)
        except Exception:
            continue
        if x.get("mint") in need and "later" in x:
            blk[x["mint"]] = x
s1 = {}
for l in open("/root/race/s1.jsonl"):
    try:
        x = json.loads(l)
    except Exception:
        continue
    if x.get("mint") in need and "rows" in x:
        s1[x["mint"]] = x
nh = 0
for r in H:
    b = blk.get(r["mint"])
    if not b:
        continue
    s = s1.get(r["mint"])
    tl = timeline(b, s, hist_path=r["path"])
    o = dict(set="hist", mint=r["mint"], slot=r["slot"], bt=r.get("bt"), in_rand=r["in_rand"], his=r["his"], dev=r["dev_sol"],
             glued=r["glued"], gsol=r["gsol"], n_len=r["n_len"], fired=None, has_s1=bool(s),
             race=r["out2s_nx"] >= 3 and r["out2s_solx"] >= 3, out2s_nx=r["out2s_nx"], out2s_solx=r["out2s_solx"], creator=b["creator"])
    o.update(tl)
    U.append(o)
    nh += 1
print("hist", len(H), "joined", nh, "with s1", sum(1 for o in U if o["has_s1"]), flush=True)


def fwdset(tag, log, oc, paths):
    rows = build(log, oc, paths, verbose=True)
    rows = [o for o in rows if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
    ocd = {}
    for l in open(oc):
        try:
            x = json.loads(l)
            ocd[x["mint"]] = x
        except Exception:
            pass
    eng = {}
    for l in open(paths):
        try:
            x = json.loads(l)
            eng[x["mint"]] = x.get("path")
        except Exception:
            pass
    n = 0
    for r in rows:
        rec = ocd[r["mint"]]
        tl = timeline(rec["b"], rec["s"], eng_path=eng.get(r["mint"]))
        o = dict(set=tag, mint=r["mint"], slot=r["slot"], bt=r.get("bt"), in_rand=True, his=r["his"], dev=r["dev_sol"], glued=r["glued"],
                 gsol=r["gsol"], n_len=r["n_len"], fired=r["fired"], has_s1=True, race=r["out2s_nx"] >= 3 and r["out2s_solx"] >= 3,
                 out2s_nx=r["out2s_nx"], out2s_solx=r["out2s_solx"], has_path=r["has_path"], eng_outs=r["eng_outs"], creator=rec["b"]["creator"])
        o.update(tl)
        U.append(o)
        n += 1
    print(tag, n, flush=True)


fwdset("fwd", "/root/race/paper_fwd.log", "/root/race/fwd_onchain.jsonl", "/root/race/paths_fwd.jsonl")
fwdset("night", "/root/racedeep/snap/paper_night.log", "/root/racedeep/snap/night_onchain.jsonl", "/root/racedeep/snap/paths_night.jsonl")
# the night run started 20:09 UTC while forward run 1 ran to ~21:14: drop night launches inside the fwd window (no train/test overlap)
fmax = max(o["slot"] for o in U if o["set"] == "fwd")
nb = len(U)
U = [o for o in U if not (o["set"] == "night" and o["slot"] <= fmax)]
print("dropped night launches overlapping fwd run 1:", nb - len(U), "| fwd max slot", fmax)
pickle.dump(U, open("/root/racedeep/U.pkl", "wb"))
print("total", len(U), collections.Counter(o["set"] for o in U))
