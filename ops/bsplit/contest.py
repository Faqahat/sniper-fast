# READ-ONLY: why do we only land on quiet launches? Compare contest level of launches our engine FIRES on vs ones it
# SKIPS because of the dev-buy read (cap-family BuyV2/Buy/BuyV3 dev buy -> engine reads 0 SOL).
# Data: /root/indep/creates.jsonl (create slot S rebuilt in order). Contest = outside (non-glued) buyers in slot S.
import sys, json, random, statistics as st, concurrent.futures as cf
sys.path.insert(0, "/root/indep")
from common import rpc, b58dec, PUMP
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
SIZED = {bytes([0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88]): "quote_in_v3", bytes([0xc2, 0xab, 0x1c, 0x46, 0x68, 0x4d, 0x5b, 0x2f]): "quote_in_v2",
         bytes([0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f]): "exact_sol_in"}
CAP = {bytes([0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea]): "buy", bytes([0xb8, 0x17, 0xee, 0x61, 0x67, 0xc5, 0xd3, 0x3d]): "buy_v2",
       bytes([0x07, 0x05, 0x1d, 0xc4, 0xf5, 0x17, 0x65, 0x50]): "buy_v3"}
R = []
for l in open("/root/indep/creates.jsonl"):
    try:
        r = json.loads(l)
    except Exception:
        continue
    if r.get("missing") or "create" not in r:
        continue
    R.append(r)
random.seed(7)
random.shuffle(R)
R = R[:int(sys.argv[1]) if len(sys.argv) > 1 else 1500]


def one(r):
    mint = r["mint"]
    cev = r.get("cev") or {}
    host = (cev.get("uri") or "").split("://")[-1].split("/")[0]
    # contest in S: rows after the create, glued run first, then outside buys
    rows = sorted([x for x in r.get("rows", []) if x.get("slot") == r["slot"]], key=lambda x: x["idx"])
    glued, run, outside, out_sol, his = 0, True, set(), 0, False
    for x in rows:
        buys = [e for e in x.get("ev", []) if e["buy"]]
        okk = not x.get("err")
        if run:
            if buys and okk:
                glued += 1
                if any(e["user"] == W for e in buys): his = True
                continue
            run = False
        if buys and okk:
            outside.add(x["payer"]); out_sol += sum(e["sol"] for e in buys)
            if any(e["user"] == W for e in buys): his = True
    for x in r.get("nrows", []):
        if any(e["buy"] and e["user"] == W for e in x.get("ev", [])): his = True
    # dev-buy instruction type from the create tx
    t = rpc("getTransaction", [r["create"]["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    kind, eng_dev = "none", 0
    true_dev = sum(e["sol"] for e in r["create"].get("ev", []) if e["buy"]) / 1e9
    if isinstance(t, dict) and "meta" in t:
        msg = t["transaction"]["message"]
        la = t["meta"].get("loadedAddresses") or {}
        keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        for ix in msg["instructions"]:
            if keys[ix["programIdIndex"]] != PUMP:
                continue
            d = b58dec(ix["data"])
            if d[:8] in SIZED:
                kind = SIZED[d[:8]]; eng_dev = max(eng_dev, int.from_bytes(d[8:16], "little") / 1e9)
            elif d[:8] in CAP and kind == "none":
                kind = CAP[d[:8]] + (" UNLIMITED" if int.from_bytes(d[16:24], "little") > 10**15 else "")
    else:
        kind = "?"
    return dict(mint=mint, host=host, bl=(host in BOT or host.endswith(".trycloudflare.com")), true_dev=true_dev, eng_dev=eng_dev,
                kind=kind, glued=glued, n_out=len(outside), out_sol=out_sol / 1e9, his=his, client=r.get("client"))


with cf.ThreadPoolExecutor(8) as ex:
    D = [x for x in ex.map(one, R) if x]
json.dump(D, open("/root/bsplit/contest.json", "w"))


def grp(name, g):
    if not g:
        print(f"{name:58} n=0"); return
    c = [x for x in g if x["n_out"] >= 1]
    print(f"{name:58} n={len(g):4} | contested (>=1 outsider in S) {len(c)/len(g):4.0%} | outsiders med {st.median(x['n_out'] for x in g):.0f} "
          f"mean {st.mean(x['n_out'] for x in g):.1f} | 4yFAz bought {sum(x['his'] for x in g):3} ({sum(x['his'] for x in g)/len(g):.1%})")


ok_host = [x for x in D if not x["bl"] and x["host"]]
FIRE = [x for x in ok_host if 0.5 <= x["eng_dev"] <= 8]
BUG = [x for x in ok_host if x["eng_dev"] < 0.5 and 0.5 <= x["true_dev"] <= 8]
print(f"sample {len(D)} creates | dev-buy instruction types: " + ", ".join(f"{k}:{v}" for k, v in sorted(__import__('collections').Counter(x['kind'] for x in D).items(), key=lambda kv: -kv[1])))
grp("ALL creates", D)
grp("WE FIRE (host ok, engine dev 0.5-8)", FIRE)
grp("SKIPPED BY DEV BUG (host ok, real dev 0.5-8, engine reads <0.5)", BUG)
grp("  ..of which UNLIMITED cap buys", [x for x in BUG if "UNLIMITED" in x["kind"]])
grp("host ok, real dev < 0.5", [x for x in ok_host if x["true_dev"] < 0.5])
grp("host ok, real dev > 8", [x for x in ok_host if x["true_dev"] > 8])
grp("bot-launchpad hosts (blacklisted)", [x for x in D if x["bl"]])
