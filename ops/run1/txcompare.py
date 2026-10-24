# READ-ONLY (host; public RPCs): side-by-side anatomy of buy transactions — ours vs the peers that landed earlier in the
# same create slot. Per tx: version, size, CU limit / used / price, priority fee, tips, priority per requested CU, and
# every WRITABLE account (labelled by its place in the pump instruction). Then a matrix: which writable accounts each tx
# locks, so a lock that only we take (or a hot global one) stands out.
# usage: python3 txcompare.py label=sig [label=sig ...]          RPC_URLS as in bundlestudy.py
import sys, os, json, time, base64, itertools, threading, urllib.request

EPS = os.environ.get("RPC_URLS", "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com").split(",")
_rr = itertools.cycle(range(len(EPS))); _lock = threading.Lock()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB = "ComputeBudget111111111111111111111111111111"
SYS = "11111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}
# pump buy / buy_exact_sol_in account order (IDL); later positions printed by number
BUY_ACCTS = ["global", "fee_recipient", "mint", "bonding_curve", "assoc_bonding_curve", "user_ata", "user", "system_program",
             "token_program", "creator_vault", "event_authority", "pump_program", "global_volume_acc", "user_volume_acc", "fee_config", "fee_program"]
TIPMAP = json.load(open(os.environ["TIPMAP_JSON"])) if os.environ.get("TIPMAP_JSON") else {}


def rpc(meth, params, tries=10):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    for i in range(tries):
        with _lock: ep = EPS[next(_rr)]
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(ep, data=data, headers={"content-type": "application/json"}), timeout=60))
            if "error" in r: time.sleep(1 + i); continue
            return r.get("result")
        except Exception:
            time.sleep(1 + i)
    return None


def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + b


def anatomy(label, sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    raw = rpc("getTransaction", [sig, {"encoding": "base64", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    msg = t["transaction"]["message"]; meta = t["meta"]; h = msg["header"]
    static = list(msg["accountKeys"]); la = meta.get("loadedAddresses") or {}
    keys = static + la.get("writable", []) + la.get("readonly", [])
    ns, nro_s, nro_u = h["numRequiredSignatures"], h["numReadonlySignedAccounts"], h["numReadonlyUnsignedAccounts"]
    writable = set()
    for i, k in enumerate(static):
        if (i < ns and i < ns - nro_s) or (i >= ns and i < len(static) - nro_u): writable.add(k)
    writable |= set(la.get("writable", []))
    cu_limit = cu_price = None; tips = []; pump_accts = None; ix_progs = []
    allix = [(ix, True) for ix in msg["instructions"]] + [(ix, False) for inn in (meta.get("innerInstructions") or []) for ix in inn.get("instructions") or []]
    for ix, top in allix:
        pid = keys[ix["programIdIndex"]]
        if top: ix_progs.append(pid[:6])
        try: d = b58dec(ix["data"])
        except Exception: d = b""
        if pid == CB and d:
            if d[0] == 2 and len(d) >= 5: cu_limit = int.from_bytes(d[1:5], "little")
            if d[0] == 3 and len(d) >= 9: cu_price = int.from_bytes(d[1:9], "little")
        if pid == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and len(ix.get("accounts") or []) >= 2:
            dst = keys[ix["accounts"][1]]; lab = TIPMAP.get(dst) or ("nozomi" if dst.startswith(("noz", "TEMPa")) else "astralane" if dst.lower().startswith("astra") else None)
            if lab: tips.append((lab, int.from_bytes(d[4:12], "little") / 1e9))
        if pid == PUMP and pump_accts is None and len(ix.get("accounts") or []) >= 12:
            pump_accts = [keys[a] for a in ix["accounts"]]
    label_of = {}
    if pump_accts:
        for j, a in enumerate(pump_accts): label_of.setdefault(a, BUY_ACCTS[j] if j < len(BUY_ACCTS) else f"pump#{j}")
    ver = t.get("version")
    size = len(base64.b64decode(raw["transaction"][0])) if raw else None
    prio = ((meta.get("fee") or 0) - 5000 * ns) / 1e9
    return dict(label=label, sig=sig, slot=t["slot"], ver=ver, size=size, cu_limit=cu_limit, cu_used=meta.get("computeUnitsConsumed"), cu_price=cu_price,
                prio=prio, tips=tips, err=meta.get("err") is not None, writable=writable, label_of=label_of, progs=ix_progs, n_alt=len(msg.get("addressTableLookups") or []),
                n_keys=len(keys))


txs = [anatomy(*a.split("=", 1)) for a in sys.argv[1:]]
txs = [t for t in txs if t]
print(f"{'tx':16} {'ver':>6} {'bytes':>5} {'CU lim':>7} {'CU used':>7} {'uL/CU':>11} {'prio SOL':>8} {'prio/CUlim':>10} {'tips':30} {'ALTs':>4} {'#writable':>9} top-level programs")
for t in txs:
    ppc = (t["prio"] * 1e9 / t["cu_limit"]) if t["cu_limit"] else None
    print(f"{t['label'][:16]:16} {str(t['ver']):>6} {t['size'] or 0:5} {t['cu_limit'] or 0:7} {t['cu_used'] or 0:7} {t['cu_price'] or 0:11} {t['prio']:8.4f} "
          f"{(('%.1f' % ppc) if ppc else '-'):>10} {str([(a, round(b, 4)) for a, b in t['tips']])[:30]:30} {t['n_alt']:4} {len(t['writable']):9} {','.join(t['progs'])}{'  FAILED' if t['err'] else ''}")
# writable-account matrix
allw = {}
for t in txs:
    for a in t["writable"]:
        allw.setdefault(a, set()).add(t["label"])
names = {}
for t in txs:
    for a, n in t["label_of"].items(): names.setdefault(a, n)
print(f"\nWRITABLE ACCOUNTS (X = locked by that tx); {len(txs)} txs")
print(f"{'account':10} {'role':22} " + " ".join(f"{t['label'][:8]:>8}" for t in txs))
for a, who in sorted(allw.items(), key=lambda kv: (-len(kv[1]), names.get(kv[0], "~"))):
    role = names.get(a, "")
    print(f"{a[:8]:10} {role:22} " + " ".join(f"{'X' if t['label'] in who else '.':>8}" for t in txs))
