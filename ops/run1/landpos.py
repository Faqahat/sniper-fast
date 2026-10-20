# READ-ONLY, self-contained (runs on the host; RPC from $RPC_URL, default public mainnet): for one fire, where did our
# buy land inside the create slot, what price did it meet there (x the post-bundle price), and what would a SIZE SOL buy
# at exactly that position have made if sold at the end of S+1..S+K (constant-product replay of every later trade,
# others' buy SOL and sell tokens held fixed). Also the same buy right after the glued bundle (best case).
# usage: python3 landpos.py <mint> <create slot> <our buy sig> [size SOL=1.5] [landing fee SOL=0.025] [K=5] [slip-cap bps=1500]
import sys, os, json, time, base64, urllib.request

RPC = os.environ.get("RPC_URL", "https://api.mainnet-beta.solana.com")
VOTE = "Vote111111111111111111111111111111111111111"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
SELL_FEE = 0.0005
m, S, SIG = sys.argv[1], int(sys.argv[2]), sys.argv[3]
SIZE = float(sys.argv[4]) if len(sys.argv) > 4 else 1.5
LAND = float(sys.argv[5]) if len(sys.argv) > 5 else 0.025
K = int(sys.argv[6]) if len(sys.argv) > 6 else 5
CAP = int(sys.argv[7]) if len(sys.argv) > 7 else 1500


def rpc(meth, params, tries=8):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(RPC, data=data, headers={"content-type": "application/json"}), timeout=60))
            if "error" in r:
                if r["error"].get("code") in (-32007, -32009): return None
                time.sleep(1.5 * (i + 1)); continue
            return r.get("result")
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def b58enc(b):
    n = int.from_bytes(b, "big"); out = []
    while n:
        n, r = divmod(n, 58); out.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + "".join(reversed(out))


def trades(logs):
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "): continue
        try: raw = base64.b64decode(l[14:] + "===")
        except Exception: continue
        if raw[:8] != TRADE_DISC or len(raw) < 129: continue
        o = 8; mint = b58enc(raw[o:o + 32]); o += 32
        sol = int.from_bytes(raw[o:o + 8], "little"); o += 8
        tok = int.from_bytes(raw[o:o + 8], "little"); o += 8
        buy = raw[o]; o += 1
        user = b58enc(raw[o:o + 32]); o += 32 + 8
        vsol = int.from_bytes(raw[o:o + 8], "little"); o += 8
        vtok = int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=mint, sol=sol, tok=tok, buy=buy, user=user, vsol=vsol, vtok=vtok))
    return out


def pre(e):
    return (e["vsol"] - e["sol"], e["vtok"] + e["tok"]) if e["buy"] else (e["vsol"] + e["sol"], e["vtok"] - e["tok"])


tape = []          # (slot, idx, ok, sig, [trades of m])
ci = our = None; ME = None; INFO = {}


def txinfo(t):
    msg = t["transaction"]["message"]; meta = t.get("meta") or {}
    keys = list(msg["accountKeys"]) + (meta.get("loadedAddresses") or {}).get("writable", []) + (meta.get("loadedAddresses") or {}).get("readonly", [])
    pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
    gains = sorted(((post[i] - pre[i], keys[i]) for i in range(1, min(len(pre), len(post), len(keys))) if post[i] - pre[i] > 0), reverse=True)
    return dict(payer=keys[0], fee=meta.get("fee") or 0, cu=meta.get("computeUnitsConsumed"), gains=gains[:4])
for s in range(S, S + K + 1):
    b = rpc("getBlock", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False}])
    if not b: continue
    txs = [t for t in b["transactions"] if VOTE not in t["transaction"]["message"]["accountKeys"]]
    for i, t in enumerate(txs):
        sig = t["transaction"]["signatures"][0]; meta = t.get("meta") or {}
        tr = [e for e in trades(meta.get("logMessages")) if e["mint"] == m]
        if s == S and sig == SIG: our = i; ME = txinfo(t)["payer"]
        if s == S and tr: INFO[i] = txinfo(t)
        if s == S and ci is None and tr and meta.get("err") is None: ci = i      # first trade of the mint = the create (+dev buy)
        if tr or (s == S and sig == SIG): tape.append((s, i, meta.get("err") is None, sig, tr))
    if s == S: nS = len(txs)
    del b
ok = [x for x in tape if x[2] and x[4]]
# glued bundle = the create tx and the consecutive successful buys right after it
ge = ci
while any(x[0] == S and x[1] == ge + 1 and x[2] and x[4] and x[4][0]["buy"] for x in tape): ge += 1
glued = [x for x in ok if x[0] == S and x[1] <= ge]
pbV, pbT = glued[-1][4][-1]["vsol"], glued[-1][4][-1]["vtok"]
pb = pbV / pbT
fee_rate = 0.0125
before_us = [x for x in ok if x[0] == S and ge < x[1] < (our if our is not None else 10**9)]
print(f"mint {m}  S={S}  non-vote txs in S: {nS}")
for x in [x for x in ok if x[0] == S and x[1] > ge and (our is None or x[1] <= our + 40)][:12]:
    inf = INFO.get(x[1], {})
    b_ = sum(e["sol"] for e in x[4] if e["buy"]) / 1e9; s_ = sum(e["sol"] for e in x[4] if not e["buy"]) / 1e9
    print(f"   idx {x[1]:4} (+{x[1] - ge:3} after bundle) {'US ' if x[3] == SIG else '   '}{'buy %.2f' % b_ if b_ else 'sell %.2f' % s_} SOL  wallet {x[4][0]['user'][:6]}"
          f"  fee {inf.get('fee', 0)/1e9:.4f}  cu {inf.get('cu')}  credits " + " ".join(f"{g/1e9:.4f}>{d[:5]}" for g, d in inf.get('gains', [])))
print(f"create idx {ci}, glued bundle ends idx {ge} (post-bundle vsol {pbV/1e9:.2f} SOL), OUR buy idx {our}"
      f"  -> {(our - ge) if our is not None else '?'} txs after the bundle, {len(before_us)} outside trades of this mint before us "
      f"({sum(e['sol'] for x in before_us for e in x[4] if e['buy'])/1e9:.2f} SOL bought)")


def sim(entry_after):   # our buy sits right after (slot, idx) = entry_after; replay every OTHER trade from the post-bundle state
    V, T = pbV, pbT
    others = [x for x in ok if (x[0], x[1]) > (S, ge) and x[3] != SIG and not any(e["user"] == ME for e in x[4])]
    q = None; at_px = None; endst = {}
    def ins():
        nonlocal V, T, q, at_px
        at_px = (V / T) / pb
        xin = SIZE * 1e9 / (1 + fee_rate); q = T * xin / (V + xin); V += xin; T -= q
    for x in others:
        if q is None and (x[0], x[1]) > entry_after: ins()
        for e in x[4]:
            if e["buy"]: d = T * e["sol"] / (V + e["sol"]); V += e["sol"]; T -= d
            else: so = V * e["tok"] / (T + e["tok"]); V -= so; T += e["tok"]
        endst[x[0]] = (V, T)
    if q is None: ins()
    fill = (SIZE * 1e9 / q) / pb
    res = []; cur = None
    for k in range(0, K + 1):
        if S + k in endst: cur = endst[S + k]
        Vk, Tk = cur if cur else (V, T)
        proceeds = Vk * q / (Tk + q) * (1 - fee_rate) / 1e9
        res.append((k, (Vk / Tk) / pb, proceeds - SIZE - LAND - SELL_FEE))
    return at_px, fill, res, q


q_pb = sim((S, ge))[3]
q_us = sim((S, our if our is not None else ge))[3]
print(f"price cap: tokens for our spend at our spot = {q_us / q_pb:.1%} of the post-bundle quote; the cap needs >= {1 - CAP / 1e4:.0%} "
      f"-> {'PASS' if q_us >= q_pb * (1 - CAP / 1e4) else 'REFUSED'}")


for label, pos in (("right after bundle", (S, ge)), ("AT OUR LANDING", (S, our if our is not None else ge))):
    at_px, fill, res, _ = sim(pos)
    print(f"\n{label}: price there {at_px:.3f}x post-bundle, our {SIZE} SOL fill {fill:.3f}x")
    print("   " + "  ".join(f"S+{k}: px {p:.2f}x pnl {v:+.3f}" for k, p, v in res))
