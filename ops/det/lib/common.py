# READ-ONLY helpers for /root/indep: RPC, base58, tip map, block/tx parsing (pump.fun create/trade).
import json, os, re, time, base64, hashlib, urllib.request

TOK = os.environ.get("CONSTANTK_TOKEN", "")
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
MINT_AUTH = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"
VOTE = "Vote111111111111111111111111111111111111111"
SYS = "11111111111111111111111111111111"
CB = "ComputeBudget111111111111111111111111111111"
VSOL0 = 30_000_000_000
VTOK0 = 1_073_000_000_000_000
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
CREATE_DISC = hashlib.sha256(b"event:CreateEvent").digest()[:8]
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}


def floor_px(dev):
    return (VSOL0 + dev) ** 2 / (VSOL0 * VTOK0)


def rpc(m, p, tries=6, timeout=90):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(RPC, data=data, headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=timeout))
            if "error" in r:
                code = r["error"].get("code")
                # -32007 slot skipped / -32009 missing in long-term storage: definitive
                if code in (-32007, -32009, -32004) and i >= 1:
                    return {"__err": code}
                last = r["error"]
                time.sleep(0.5 * (i + 1))
                continue
            return r.get("result")
        except Exception as ex:
            last = ex
            time.sleep(0.5 * (i + 1))
    return {"__err": str(last)[:200]}


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58I[c]
    pad = len(s) - len(s.lstrip("1"))
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * pad + b


def b58enc(b):
    n = int.from_bytes(b, "big")
    out = []
    while n:
        n, r = divmod(n, 58)
        out.append(B58[r])
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + "".join(reversed(out))


def load_tipmap():
    """tip account -> sender label: engine known_tip_accounts (src/send/mod.rs) first, then the catalogue."""
    m = {}
    try:
        src = open("/root/arbx-fast/src/send/mod.rs").read()
        i = src.find("pub fn known_tip_accounts")
        body = src[i:i + 60000]
        j = body.find("\n}\n")
        body = body[:j] if j > 0 else body
        cur = None
        for line in body.splitlines():
            km = re.findall(r"SendKind::(\w+)", line)
            if km and "=>" in line:
                cur = km[0].lower()
            for a in re.findall(r'"([1-9A-HJ-NP-Za-km-z]{32,44})"', line):
                if cur:
                    m.setdefault(a, cur)
        for a, n in re.findall(r'\("([1-9A-HJ-NP-Za-km-z]{32,44})",\s*"([^"]+)"\)', src):
            m.setdefault(a, n.rstrip("?"))
    except Exception:
        pass
    cat = json.load(open("/root/arbx-fast/data/sender-tip-accounts.json"))
    for k, v in cat.items():
        if not isinstance(v, dict):
            continue
        ta = v.get("tip_accounts")
        if isinstance(ta, list):
            for a in ta:
                if isinstance(a, str):
                    m.setdefault(a, k)
    # normalise names
    norm = {"jitotx": "jito", "jitobundle": "jito", "quicknode_lil_jit": "jito", "helius": "helius_sender", "iris": "astralane",
            "astralane_iris": "astralane", "lunar": "lunar", "hellomoon_lunar_lander": "lunar", "nozomi": "nozomi",
            "temporal_nozomi": "nozomi", "zeroslot": "0slot", "nodeone": "node1", "falcon": "falcon", "falcon_corvus": "falcon",
            "everstake": "everstake", "everstake_swqos": "everstake", "bloxroute": "bloxroute", "bloxroute_trader_api": "bloxroute",
            "bloxroute_legacy": "bloxroute", "jupitertx": "jupiter", "jupiter_tx": "jupiter", "bolt": "raiden_bolt", "rpcfast": "rpcfast_beam",
            "svs_lightspeed_legacy": "svs_lightspeed", "blockrazor": "blockrazor", "flashblock": "flashblock", "nextblock": "nextblock",
            "speedlanding": "speedlanding", "landx": "landx"}
    return {a: norm.get(n, n) for a, n in m.items()}


def prefix_label(dst):
    if dst.startswith("noz") or dst.startswith("TEMPa"):
        return "nozomi"
    if dst.startswith("astra"):
        return "astralane"
    if dst.startswith("moon"):
        return "lunar?"
    return None


def parse_trade(raw):
    o = 8
    mint = b58enc(raw[o:o + 32]); o += 32
    sol = int.from_bytes(raw[o:o + 8], "little"); o += 8
    tok = int.from_bytes(raw[o:o + 8], "little"); o += 8
    isbuy = raw[o]; o += 1
    user = b58enc(raw[o:o + 32]); o += 32
    o += 8
    vsol = int.from_bytes(raw[o:o + 8], "little"); o += 8
    vtok = int.from_bytes(raw[o:o + 8], "little"); o += 8
    return dict(mint=mint, sol=sol, tok=tok, buy=isbuy, user=user, vsol=vsol, vtok=vtok)


def parse_create(raw):
    try:
        o = 8
        strs = []
        for _ in range(3):
            n = int.from_bytes(raw[o:o + 4], "little"); o += 4
            strs.append(raw[o:o + n].decode("utf8", "replace")); o += n
        mint = b58enc(raw[o:o + 32]); o += 32
        o += 32  # bonding curve
        user = b58enc(raw[o:o + 32]); o += 32
        creator = b58enc(raw[o:o + 32]) if len(raw) >= o + 32 else user
        return dict(name=strs[0][:40], symbol=strs[1][:20], uri=strs[2][:200], mint=mint, user=user, creator=creator)
    except Exception:
        return None


def events(logs):
    tr, cr = [], []
    for l in logs or []:
        if l.startswith("Program data: "):
            try:
                raw = base64.b64decode(l[14:] + "===")
            except Exception:
                continue
            if raw[:8] == TRADE_DISC and len(raw) >= 8 + 32 + 8 + 8 + 1 + 32 + 8 + 8 + 8:
                tr.append(parse_trade(raw))
            elif raw[:8] == CREATE_DISC:
                c = parse_create(raw)
                if c:
                    cr.append(c)
    return tr, cr


def tx_summary(t, tipmap, full=True):
    """compact summary of a json-encoded block tx"""
    msg = t["transaction"]["message"]
    meta = t.get("meta") or {}
    keys = list(msg["accountKeys"])
    la = meta.get("loadedAddresses") or {}
    keys += la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    s = {"sig": t["transaction"]["signatures"][0], "payer": keys[0], "signers": keys[:nsig], "err": meta.get("err") is not None,
         "fee": meta.get("fee"), "cuu": meta.get("computeUnitsConsumed")}
    cu_price = cu_limit = None
    tips = []
    progs = []
    def scan_ix(ix, top):
        nonlocal cu_price, cu_limit
        try:
            pid = keys[ix["programIdIndex"]]
        except Exception:
            return
        if top:
            progs.append(pid)
        if pid == CB and top:
            try:
                raw = b58dec(ix["data"])
            except Exception:
                return
            if raw and raw[0] == 2 and len(raw) >= 5:
                cu_limit = int.from_bytes(raw[1:5], "little")
            elif raw and raw[0] == 3 and len(raw) >= 9:
                cu_price = int.from_bytes(raw[1:9], "little")
        elif pid == SYS:
            try:
                raw = b58dec(ix["data"])
            except Exception:
                return
            if len(raw) >= 12 and int.from_bytes(raw[:4], "little") == 2:
                lam = int.from_bytes(raw[4:12], "little")
                acc = ix.get("accounts") or []
                if len(acc) >= 2:
                    dst = keys[acc[1]]
                    lab = tipmap.get(dst) or prefix_label(dst)
                    if lab:
                        tips.append([lab, lam, dst[:8], 1 if top else 0])
    for ix in msg["instructions"]:
        scan_ix(ix, True)
    for inn in meta.get("innerInstructions") or []:
        for ix in inn.get("instructions") or []:
            scan_ix(ix, False)
    s["cu_price"], s["cu_limit"] = cu_price, cu_limit
    s["tips"] = tips
    kt = sorted({tipmap[k] for k in keys if k in tipmap})
    s["keytip"] = kt
    s["progs"] = [p[:6] for p in progs if p not in (CB,)]
    return s, keys


def is_vote(t):
    return VOTE in t["transaction"]["message"]["accountKeys"]


def get_block(slot):
    return rpc("getBlock", [slot, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full",
                                   "rewards": False, "commitment": "confirmed"}], timeout=120)
