#!/usr/bin/env python3
# READ-ONLY RPC: validate the shred-side decoder for DIRECT dip triggers. For a sample of trigger txs whose pump sell is a
# top-level instruction: decode each top-level pump ix (discriminator, account count, positions of mint and seller, u64 args at
# offsets 8 and 16) and compare with the tx's own TradeEvent for that mint (seller, token amount, SOL out).
# RPC = owner's endpoint (~/.config/sniper/ck_rpc_url, never printed).
# usage: python3 -I trig_decode.py trig_tx.jsonl trig_sigs.jsonl N
import sys, os, json, time, base64, random, collections, urllib.request, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
U = lambda b, o: int.from_bytes(b[o:o + 8], "little") if len(b) >= o + 8 else None
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=30))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
    return None
TX = [json.loads(l) for l in open(sys.argv[1])]
MINT = {}
for l in open(sys.argv[2]):
    e = json.loads(l)
    if e.get("sig"): MINT[e["sig"]] = e["m"]
tops = [t["sig"] for t in TX if t.get("kind") == "top" and t["sig"] in MINT]
random.Random(3).shuffle(tops); tops = tops[:int(sys.argv[3])]
def one(sig):
    mint = MINT[sig]
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    evs = []
    for l in (t["meta"].get("logMessages") or []):
        if l.startswith("Program data: "):
            x = l[14:].strip(); x += "=" * (-len(x) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 129 and b58enc(raw[8:40]) == mint:
                evs.append(dict(sol=U(raw, 40), tok=U(raw, 48), buy=raw[56], user=b58enc(raw[57:89])))
    if not evs:
        for inn in (t["meta"].get("innerInstructions") or []):
            for ix in inn["instructions"]:
                if keys[ix["programIdIndex"]] == PUMP:
                    raw = b58dec(ix["data"])
                    if raw[8:16] == TD and b58enc(raw[16:48]) == mint: evs.append(dict(sol=U(raw, 48), tok=U(raw, 56), buy=raw[64], user=b58enc(raw[65:97])))
    out = []
    sells = [e for e in evs if e["buy"] == 0]
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != PUMP: continue
        accs = [keys[a] for a in ix["accounts"]]
        if mint not in accs: continue
        d = b58dec(ix["data"]); a8, a16 = U(d, 8), U(d, 16)
        ev = next((e for e in sells if e["user"] in accs), sells[0] if sells else None)
        out.append(dict(sig=sig, disc=d[:8].hex(), nacc=len(accs), dlen=len(d), mintpos=accs.index(mint), signer=msg["accountKeys"][0],
                        userpos=accs.index(ev["user"]) if ev and ev["user"] in accs else -1, signer_is_user=bool(ev and ev["user"] == msg["accountKeys"][0]),
                        a8_eq_tok=bool(ev and a8 == ev["tok"]), a16_le_sol=bool(ev and a16 is not None and a16 <= ev["sol"]), n_sell_ev=len(sells), n_ev=len(evs)))
    return out
R = []
with cf.ThreadPoolExecutor(16) as ex:
    for o in ex.map(one, tops):
        if o: R += o
json.dump(R, open("/home/moiz/sniper/ops/overnight/dipshadow/trig_decode.json", "w"))
by = collections.defaultdict(list)
for r in R: by[r["disc"]].append(r)
print("direct trigger txs decoded:", len(tops), "top-level pump ixs on the mint:", len(R))
for d, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    c = lambda f: collections.Counter(f(r) for r in v).most_common(3)
    print(f"  {d} n {len(v):4d} | accounts {c(lambda r: r['nacc'])} | data len {c(lambda r: r['dlen'])} | mint pos {c(lambda r: r['mintpos'])} | seller pos {c(lambda r: r['userpos'])}"
          f" | a8 == tokens sold {sum(r['a8_eq_tok'] for r in v) / len(v):.0%} | a16 <= SOL out {sum(r['a16_le_sol'] for r in v) / len(v):.0%} | signer is seller {sum(r['signer_is_user'] for r in v) / len(v):.0%}"
          f" | txs with >1 sell event {sum(1 for r in v if r['n_sell_ev'] > 1)}")
