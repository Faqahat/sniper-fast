#!/usr/bin/env python3
"""REPLAY_065 step 4 (READ-ONLY RPC): the slippage limit of every other wallet's trade inside our hold windows.
For each signature: getTransaction (json), every pump.fun instruction (outer or inner/CPI) that names the mint -> its
discriminator and first two u64 args, whether it is the outer instruction (the limit was fixed when the tx was signed) or
a CPI from another program (the args may be computed on chain), and the tx's own TradeEvents of the mint (to match).
RPC = the owner's endpoint (~/.config/sniper/ck_rpc_url, never printed). Resumable: appends to a cache jsonl.
usage: fetch.py SIGS.json OUT.jsonl     (SIGS.json = [[sig, mint], ...])"""
import sys, os, json, time, base64, urllib.request, threading, concurrent.futures as cf

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
CPI_EV = bytes.fromhex("e445a52e51cb9a1d")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()


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
            req = urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if "result" in r and r["result"] is not None: return r["result"]
        except Exception:
            pass
        time.sleep(0.4 * (i + 1))
    return None


U = lambda raw, a: int.from_bytes(raw[a:a + 8], "little")


def events_of(raw_list, mint):
    out = []
    for raw in raw_list:
        if raw[:8] == CPI_EV: raw = raw[8:]
        if raw[:8] == TD and len(raw) >= 129 and b58(raw[8:40]) == mint:
            out.append(dict(sol=U(raw, 40), tok=U(raw, 48), buy=raw[56] == 1))
    return out


def one(sig, mint):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return dict(sig=sig, mint=mint, kind="nofetch")
    msg = t["transaction"]["message"]; meta = t["meta"]; la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    outer = msg["instructions"]
    inner = {x["index"]: x["instructions"] for x in (meta.get("innerInstructions") or [])}
    ixs = []                                     # (outer index, inner position or -1, program, accounts, data)
    for k, ix in enumerate(outer):
        ixs.append((k, -1, keys[ix["programIdIndex"]], [keys[a] for a in ix["accounts"]], b58d(ix["data"])))
        for q, jx in enumerate(inner.get(k, [])):
            ixs.append((k, q, keys[jx["programIdIndex"]], [keys[a] for a in jx["accounts"]], b58d(jx["data"])))
    pump = []; ev_cpi = []; ev_log = []
    for k, q, prog, accs, raw in ixs:
        if prog != PUMP: continue
        if raw[:8] == CPI_EV: ev_cpi.append(raw); continue
        if mint not in accs or len(raw) < 24: continue
        pump.append(dict(o=k, q=q, outer_prog=keys[outer[k]["programIdIndex"]], disc=raw[:8].hex(), a1=U(raw, 8), a2=U(raw, 16), n=len(raw)))
    for l in (meta.get("logMessages") or []):
        if l.startswith("Program data: "):
            x = l[14:].strip(); x += "=" * (-len(x) % 4)
            try: ev_log.append(base64.b64decode(x))
            except Exception: pass
    # pump emits its TradeEvent either as a self-CPI (newer) or in the logs (older): take one source, never both
    evs = events_of(ev_cpi, mint) or events_of(ev_log, mint)
    return dict(sig=sig, mint=mint, kind="ok", err=meta.get("err"), slot=t.get("slot"), pump=pump, ev=evs, signer=keys[0],
                outer_progs=sorted({keys[ix["programIdIndex"]] for ix in outer}))


if __name__ == "__main__":
    SIGS = json.load(open(sys.argv[1])); OUT = sys.argv[2]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            try:
                r = json.loads(l)
                if r.get("kind") != "nofetch": done.add(r["sig"])
            except Exception: pass
    todo = [(s, m) for s, m in SIGS if s not in done]
    todo = list(dict(todo).items())
    print(f"to fetch: {len(todo)} (already {len(done)})", flush=True)
    lock = threading.Lock(); n = 0; t0 = time.time()
    with open(OUT, "a") as f, cf.ThreadPoolExecutor(16) as ex:
        for r in ex.map(lambda sm: one(*sm), todo):
            with lock:
                f.write(json.dumps(r) + "\n"); n += 1
                if n % 500 == 0: f.flush(); print(f"  {n}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print(f"done {n} in {time.time() - t0:.0f}s", flush=True)
