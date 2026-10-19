#!/usr/bin/env python3
"""Shared helpers for the profit backtest: staked-RPC client (threaded, cached), b58, PDA,
create_v2 parsing, and bonding-curve trajectory reconstruction (anchored at the create slot).
Ported faithfully from arbx-fast/sketch/shadow/shadow.py + src/snipe.rs field offsets."""
import os, json, time, hashlib, urllib.request, urllib.error, threading

RPC = os.environ["RPC"]
PUMP_B58 = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
MINT_AUTHORITY = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"  # global PDA on every create -> pure create stream
CREATE_V2 = "d6904cec5f8b31b4"; CREATE = "181ec828051c0777"
# pump buy discriminators (src/snipe.rs). SOL-at-8: spendable is data[8:16]; SOL-at-16: data[16:24].
DEV_BUY_SOL_AT_8 = {"e1f7501ed5b38488", "c2ab1c46684d5b2f", "38fc74089edfcd5f"}
DEV_BUY_SOL_AT_16 = {"66063d1201daebea", "b817ee6167c5d33d", "07051dc4f5176550"}
CACHE = "/root/profit_backtest/cache"; os.makedirs(CACHE, exist_ok=True)

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58dec(s):
    n = 0
    for c in s: n = n*58 + _B58.index(c)
    return (b"\x00"*(len(s)-len(s.lstrip("1")))) + (n.to_bytes((n.bit_length()+7)//8, "big") if n else b"")
def b58enc(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = _B58[r]+s
    return "1"*(len(b)-len(b.lstrip(b"\x00"))) + s

# ---- PDA (ed25519 on-curve test) for bonding_curve derivation ----
p = 2**255-19; d = (-121665*pow(121666, p-2, p)) % p; I = pow(2, (p-1)//4, p)
def _oc(b):
    y = int.from_bytes(b, "little"); sg = (y >> 255) & 1; y &= (1 << 255)-1
    if y >= p: return False
    u = (y*y-1) % p; v = (d*y*y+1) % p; v3 = v*v*v % p; v7 = v3*v3*v % p
    x = u*v3 % p*pow(u*v7 % p, (p-5)//8, p) % p; vx2 = v*x*x % p
    if vx2 == u % p: pass
    elif vx2 == (-u) % p: x = x*I % p
    else: return False
    if x == 0 and sg: return False
    return True
def _fpa(seeds, prog):
    for bump in range(255, -1, -1):
        h = hashlib.sha256()
        for s in seeds: h.update(s)
        h.update(bytes([bump])); h.update(prog); h.update(b"ProgramDerivedAddress")
        c = h.digest()
        if not _oc(c): return c
PUMP = b58dec(PUMP_B58)
def bonding_curve_of(mint):
    return b58enc(_fpa([b"bonding-curve", b58dec(mint)], PUMP))

# ---- threaded RPC with retry + jsonrpc; getTransaction disk-cached ----
_tls = threading.local()
def rpc(m, pr, timeout=60):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": pr}).encode()
    for a in range(7):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=timeout))
            if "result" in r: return r["result"]
            # jsonrpc error (e.g. slot skipped) -> treat as None but don't hammer
            return None
        except urllib.error.HTTPError as e:
            time.sleep(1.3*(a+1) if e.code == 429 else 0.5)
        except Exception:
            time.sleep(0.4*(a+1))
    return None

def gettx(sig):
    f = os.path.join(CACHE, sig+".json")
    if os.path.exists(f):
        try: return json.load(open(f))
        except Exception: pass
    tx = rpc("getTransaction", [sig, {"maxSupportedTransactionVersion": 1, "encoding": "jsonParsed"}])
    try: json.dump(tx, open(f, "w"))
    except Exception: pass
    return tx

def _keys(tx):
    """full account-key list (static + loaded) aligned with balance arrays."""
    msg = tx["transaction"]["message"]
    ks = [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]]
    la = tx.get("meta", {}).get("loadedAddresses") or {}
    return ks + list(la.get("writable", [])) + list(la.get("readonly", []))

# ---- create_v2 feature extraction (src/snipe.rs parse_create_args offsets) ----
def parse_create(tx):
    """Returns dict with mint, bonding_curve, creator, flags, dev_buy (SOL, curve-delta truth),
    dev_buy_wire (SOL, from bundled buy ix), entry_px, create_slot, cosnipers_in_create_tx."""
    if not tx or not tx.get("meta") or tx["meta"].get("err"): return None
    msg = tx["transaction"]["message"]; keys = _keys(tx)
    meta = tx["meta"]
    # find the create instruction
    cre = None
    for ix in msg.get("instructions", []):
        pid = ix.get("programId")
        if pid != PUMP_B58: continue
        dd = b58dec(ix.get("data", ""))
        if dd[:8].hex() in (CREATE_V2, CREATE):
            cre = (ix, dd); break
    if not cre: return None
    ix, dd = cre
    accs = ix.get("accounts", [])
    if len(accs) < 6: return None
    mint, bonding_curve, creator = accs[0], accs[2], accs[5]
    # parse args: skip 3 strings, creator(32), then flags
    is_v2 = dd[:8].hex() == CREATE_V2
    mayhem = cashback = holder_reward = 0; feebps = 0
    if is_v2:
        q = 8
        try:
            for _ in range(3):
                ln = int.from_bytes(dd[q:q+4], "little"); q += 4+ln
            q += 32  # creator pubkey
            mayhem = dd[q]; cashback = dd[q+1]
            feebps = int.from_bytes(dd[q+2:q+10], "little"); holder_reward = dd[q+10]
        except Exception:
            pass
    # dev_buy (curve-delta truth): bonding_curve lamports delta in the create tx (positive = SOL in)
    bc = bonding_curve
    dev_buy = 0.0; token_recv = 0.0
    if bc in keys:
        idx = keys.index(bc)
        dsol = (meta["postBalances"][idx]-meta["preBalances"][idx])/1e9
        dev_buy = max(0.0, dsol)  # SOL into curve from dev buy
    # dev tokens received = the CREATOR's post holding of this mint (the bundled dev buy).
    # NB: the curve holds ~793M and a separate reserve/escrow holds the full 1e9 supply — both excluded
    # by matching owner==creator.
    token_recv = sum(float(t["uiTokenAmount"]["uiAmountString"] or 0)
                     for t in meta.get("postTokenBalances", [])
                     if t.get("mint") == mint and t.get("owner") == creator)
    entry_px = (dev_buy/token_recv) if token_recv > 1e-9 and dev_buy > 1e-12 else None
    # dev_buy_wire: read from the bundled buy instruction (what our live filter uses)
    dev_buy_wire = 0.0; unbounded = False
    for i2 in msg.get("instructions", []):
        if i2.get("programId") != PUMP_B58: continue
        d2 = b58dec(i2.get("data", "")); disc = d2[:8].hex()
        off = 8 if disc in DEV_BUY_SOL_AT_8 else (16 if disc in DEV_BUY_SOL_AT_16 else None)
        if off is None: continue
        v = int.from_bytes(d2[off:off+8], "little") if len(d2) >= off+8 else 0
        if v == 0xFFFFFFFFFFFFFFFF: unbounded = True
        else: dev_buy_wire = max(dev_buy_wire, v/1e9)
    return {"mint": mint, "bonding_curve": bonding_curve, "creator": creator,
            "mayhem": int(mayhem), "cashback": int(cashback), "creator_fee_bps": int(feebps),
            "holder_reward": int(holder_reward), "is_v2": is_v2,
            "dev_buy": dev_buy, "dev_buy_wire": (1e18 if unbounded else dev_buy_wire),
            "token_recv": token_recv, "entry_px": entry_px,
            "create_slot": tx.get("slot"), "blockTime": tx.get("blockTime")}

# ---- trajectory: bonding-curve trades, anchored at create slot (port of shadow.trajectory) ----
def trajectory(mint, create_slot, win=60, max_trades=80, max_pages=14):
    bc = bonding_curve_of(mint)
    all_sigs = []; before = None; pages = 0; reached = False
    while pages < max_pages:
        pr = [bc, {"limit": 1000}]
        if before: pr[1]["before"] = before
        ch = rpc("getSignaturesForAddress", pr)
        if not ch: break
        all_sigs += ch; before = ch[-1]["signature"]; pages += 1
        if len(ch) < 1000: reached = True; break           # reached oldest (the create)
        if ch[-1]["slot"] <= create_slot: reached = True; break
    sigs = [s for s in all_sigs if not s["err"] and create_slot <= s["slot"] <= create_slot+win]
    sigs.sort(key=lambda s: (s["slot"], s["signature"]))
    series = []; buyers = set(); cosnipers_slot0 = 0
    for s in sigs[:max_trades]:
        tx = gettx(s["signature"])
        if not tx or not tx.get("meta"): continue
        meta = tx["meta"]; keys = _keys(tx)
        def tok(owner):
            pre = sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("preTokenBalances", []) if t.get("owner") == owner)
            post = sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("postTokenBalances", []) if t.get("owner") == owner)
            return post-pre
        dtok = tok(bc)
        dsol = 0.0
        if bc in keys:
            idx = keys.index(bc); dsol = (meta["postBalances"][idx]-meta["preBalances"][idx])/1e9
        if dtok > 0 and dsol > 0:
            continue  # the CREATE tx (curve minted the full supply AND dev buy) — not a tradeable row
        if abs(dtok) > 0 and abs(dsol) > 1e-9:
            px = abs(dsol)/abs(dtok)
            series.append((s["slot"], tx.get("blockTime"), px, dsol))
            if s["slot"] == create_slot and dsol > 0:   # a buy in the create slot
                cosnipers_slot0 += 1
    return {"series": [(a, b, c) for (a, b, c, _d) in series], "reached_floor": reached,
            "cosnipers_slot0": max(0, cosnipers_slot0-1)}  # minus the dev buy itself
