#!/usr/bin/env python3
# Slippage-aware replay, step 2 (READ-ONLY RPC): for each follower buy tx, decode the pump.fun buy instruction it ran
# (outer or inner/CPI) and its slippage limit, checked against the tx's own TradeEvent:
#   "sol": spend a fixed SOL amount, needs >= a2 tokens out (buy_exact_sol_in style; fails BuySlippageBelowMinTokensOut)
#   "tok": buy exactly a1 tokens, pays at most a2 SOL incl. fees (buy style; fails TooMuchSolRequired)
#   "unk": no pump buy ix decoded / args don't match the event (kept as an always-fill buy in the replay)
# RPC = owner's endpoint (~/.config/sniper/ck_rpc_url, never printed). Resumable: appends to slip_args.jsonl.
# usage: python3 -I slip_fetch.py slip_sigs_10.json
import sys, os, json, time, base64, urllib.request, threading, concurrent.futures as cf
SIGS = json.load(open(sys.argv[1])); OUT = os.environ.get("SLIP_OUT", "/home/moiz/sniper/ops/overnight/sel/slip_args_sel.jsonl")
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58d(s):
    n = 0
    for ch in s: n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=30))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
    return None
U = lambda raw, a: int.from_bytes(raw[a:a + 8], "little")
def one(sig, mint):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return dict(sig=sig, mint=mint, kind="nofetch")
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    ev = None
    for l in (t["meta"].get("logMessages") or []):
        if l.startswith("Program data: "):
            x = l[14:].strip(); x += "=" * (-len(x) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 129 and b58(raw[8:40]) == mint and raw[56] == 1: ev = (U(raw, 40), U(raw, 48)); break
    ixs = [ix for ix in msg["instructions"]] + [ix for inn in (t["meta"].get("innerInstructions") or []) for ix in inn["instructions"]]
    if ev is None:
        for ix in ixs:      # event via self-CPI (no log)
            if keys[ix["programIdIndex"]] == PUMP:
                raw = b58d(ix["data"])
                if len(raw) > 16 and raw[8:16] == TD and b58(raw[16:48]) == mint and raw[64] == 1: ev = (U(raw, 48), U(raw, 56)); break
    cands = []
    for ix in ixs:
        if keys[ix["programIdIndex"]] != PUMP or mint not in [keys[a] for a in ix["accounts"]]: continue
        raw = b58d(ix["data"])
        if len(raw) >= 24 and raw[8:16] != TD: cands.append((raw[:8].hex(), U(raw, 8), U(raw, 16)))
    if ev is None: return dict(sig=sig, mint=mint, kind="noevent", ix=cands[:2])
    sol, tok = ev
    for d, a1, a2 in cands:
        if a1 == tok: return dict(sig=sig, mint=mint, kind="tok", disc=d, a1=a1, a2=a2, sol=sol, tok=tok)
        if tok >= a2 and a1 >= sol: return dict(sig=sig, mint=mint, kind="sol", disc=d, a1=a1, a2=a2, sol=sol, tok=tok)
    return dict(sig=sig, mint=mint, kind="unk", ix=cands[:2], sol=sol, tok=tok)
if __name__ == "__main__":
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            try: done.add(json.loads(l)["sig"])
            except Exception: pass
    todo = [(s, m) for m, v in SIGS.items() for s in v if s not in done]
    todo = list(dict(todo).items())
    print(f"to fetch: {len(todo)} (already {len(done)})", flush=True)
    lock = threading.Lock(); n = 0; t0 = time.time()
    with open(OUT, "a") as f, cf.ThreadPoolExecutor(24) as ex:
        for r in ex.map(lambda sm: one(*sm), todo):
            with lock:
                f.write(json.dumps(r) + "\n"); n += 1
                if n % 2000 == 0: f.flush(); print(f"  {n}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print(f"done {n} in {time.time() - t0:.0f}s", flush=True)
