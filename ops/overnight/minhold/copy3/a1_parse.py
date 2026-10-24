#!/usr/bin/env python3
# parse raw getTransaction JSON of a wallet (raw/<w8>.jsonl.gz) into compact per-tx rows -> out/chain_<w8>.json
# per tx: slot, time, ok, fee payer, is the wallet a signer, top-level programs, all invoked programs, pump TradeEvents (all users),
# wallet NATIVE SOL change + wallet WSOL token change (pump v2 trades settle in WSOL: real PnL = native + WSOL),
# wallet USDC change (some wallets trade through a USDC router), wallet token changes (other mints), SOL counterparties (other accounts' balance deltas), tips (transfers to known tip accounts),
# priority fee (compute-unit price x limit), compute budget.
import sys, os, json, gzip, base64, collections
W = sys.argv[1] if __name__ == "__main__" else None; W8 = W[:8] if W else None
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"; USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; BI = {c: i for i, c in enumerate(B58)}
def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58d(s):
    n = 0
    for ch in s: n = n * 58 + BI[ch]
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
U = lambda raw, a: int.from_bytes(raw[a:a + 8], "little")
def ev_decode(raw):
    if len(raw) < 113 or raw[:8] != TD: return None
    return dict(mint=b58e(raw[8:40]), sol=U(raw, 40), tok=U(raw, 48), buy=raw[56] == 1, user=b58e(raw[57:89]), vsol=U(raw, 97), vtok=U(raw, 105))
def parse(t, w=None):
    global W
    if w: W = w
    msg = t["transaction"]["message"]; meta = t["meta"]; la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]; signers = keys[:nsig]
    wi = keys.index(W) if W in keys else None
    dn = (meta["postBalances"][wi] - meta["preBalances"][wi]) if wi is not None and wi < len(meta["postBalances"]) else 0
    # token balance changes of accounts OWNED by the wallet
    tb = collections.defaultdict(int)
    for side, sgn in (("preTokenBalances", -1), ("postTokenBalances", 1)):
        for b in meta.get(side) or []:
            if b.get("owner") == W:
                tb[b["mint"]] += sgn * int(b["uiTokenAmount"]["amount"])
    dw = tb.pop(WSOL, 0); du = tb.pop(USDC, 0)
    toks = {m: v for m, v in tb.items() if v}
    top = [keys[ix["programIdIndex"]] for ix in msg["instructions"]]
    inv = []
    for l in meta.get("logMessages") or []:
        if l.startswith("Program ") and " invoke [" in l:
            p = l.split()[1]
            if p not in inv: inv.append(p)
    evs = []
    for l in meta.get("logMessages") or []:
        if l.startswith("Program data: "):
            x = l[14:].split()[0]; x += "=" * (-len(x) % 4)
            try: e = ev_decode(base64.b64decode(x))
            except Exception: e = None
            if e: evs.append(e)
    allix = [(0, ix) for ix in msg["instructions"]] + [(1, ix) for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]
    if not evs:
        for _, ix in allix:
            if keys[ix["programIdIndex"]] == PUMP:
                try: raw = b58d(ix["data"])
                except Exception: continue
                if len(raw) > 16 and raw[8:16] == TD:
                    e = ev_decode(raw[8:])
                    if e: evs.append(e)
    cup = 0; cul = None; tips = []; xfers = []
    for lvl, ix in allix:
        p = keys[ix["programIdIndex"]]
        try: d = b58d(ix["data"])
        except Exception: continue
        if p == CB and d and lvl == 0:
            if d[0] == 3: cup = int.from_bytes(d[1:9], "little")
            elif d[0] == 2: cul = int.from_bytes(d[1:5], "little")
        elif p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and len(ix["accounts"]) >= 2:
            a, b = keys[ix["accounts"][0]], keys[ix["accounts"][1]]; lam = U(d, 4)
            if b in TIP: tips.append((TIP[b], lam, a == W))
            elif a == W or b == W: xfers.append((a, b, lam, lvl))
    # SOL counterparties: other accounts whose native balance moved opposite to the wallet's
    cp = {}
    for k, (pre, post) in enumerate(zip(meta["preBalances"], meta["postBalances"])):
        if k < len(keys) and keys[k] != W and post != pre: cp[keys[k]] = post - pre
    if cul is None: cul = 200000 * max(1, sum(1 for p in top if p not in (CB,)))
    return dict(sig=t["sig"], slot=t["slot"], bt=t.get("blockTime"), ok=meta["err"] is None, err=json.dumps(meta["err"]) if meta["err"] else None,
                payer=keys[0], w_signer=W in signers, signers=signers, fee=meta["fee"], dn=dn, dw=dw, du=du, toks=toks, top=top, inv=inv,
                evs=evs, wev=[e for e in evs if e["user"] == W], cup=cup, cul=cul, prio=cup * cul / 1e6 / 1e9, tips=tips, xfers=xfers,
                cp=dict(sorted(cp.items(), key=lambda kv: -abs(kv[1]))[:8]), cu=meta.get("computeUnitsConsumed"), nix=len(msg["instructions"]))
if __name__ == "__main__":
    rows = []; seen = set()
    for l in gzip.open(f"raw/{W8}.jsonl.gz", "rt"):
        try: t = json.loads(l)
        except Exception: continue
        if t["sig"] in seen: continue
        seen.add(t["sig"]); rows.append(parse(t))
    rows.sort(key=lambda r: r["slot"])
    json.dump(rows, open(f"out/chain_{W8}.json", "w"))
    print(W8, "rows", len(rows))
