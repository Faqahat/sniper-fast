# REVIEW READ-ONLY: decode the engine's real signed buy txs (dumped by the junk run, never sent), check them, and
# simulateTransaction them (signature ZEROED, sigVerify=false, replaceRecentBlockhash) - nothing is broadcast.
import sys, json, base64, struct
sys.path.insert(0, "/root/indep")
from common import rpc, b58enc, b58dec, VSOL0, VTOK0
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
ATAP = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
BUYD = bytes([0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88])
TIPS = {}
for name, lst in json.load(open(sys.argv[2])).items():
    for a in lst: TIPS[a] = name
def cu16(b, o):
    v = 0; s = 0
    while True:
        x = b[o]; o += 1; v |= (x & 0x7f) << s; s += 7
        if x < 0x80: return v, o
def parse(raw):
    ns, o = cu16(raw, 0); sigs = [raw[o + 64 * i:o + 64 * (i + 1)] for i in range(ns)]; o += 64 * ns
    m0 = o; ver = raw[o]; assert ver == 0x80, "not v0"; o += 1
    hdr = raw[o:o + 3]; o += 3
    nk, o = cu16(raw, o); keys = [b58enc(raw[o + 32 * i:o + 32 * (i + 1)]) for i in range(nk)]; o += 32 * nk
    bh = b58enc(raw[o:o + 32]); o += 32
    ni, o = cu16(raw, o); ixs = []
    for _ in range(ni):
        p = raw[o]; o += 1
        na, o = cu16(raw, o); acc = list(raw[o:o + na]); o += na
        nd, o = cu16(raw, o); dofs = o; data = raw[o:o + nd]; o += nd
        ixs.append(dict(prog=keys[p], acc=acc, data=data, dofs=dofs))
    nl, o = cu16(raw, o)
    return dict(sigs=sigs, msg_off=m0, hdr=hdr, keys=keys, bh=bh, ixs=ixs, nlut=nl)
def floor_px(dev): return (VSOL0 + dev) ** 2 / (VSOL0 * VTOK0)
rows = [json.loads(l) for l in open(sys.argv[1])]
bh_first = {}
try:
    for l in open(sys.argv[3]):
        t, h = l.split(); bh_first.setdefault(h, int(t))
except Exception: pass
nsim = int(sys.argv[4]) if len(sys.argv) > 4 else 6
bad = 0
for k, r in enumerate(rows):
    raw = base64.b64decode(r["raw"]); t = parse(raw)
    keys = t["keys"]; nsig = t["hdr"][0]
    cul = cup = None; tips = []; atas = []; buy = None; other = []
    for ix in t["ixs"]:
        d = ix["data"]
        if ix["prog"] == CB:
            if d[0] == 2: cul = struct.unpack("<I", d[1:5])[0]
            elif d[0] == 3: cup = struct.unpack("<Q", d[1:9])[0]
        elif ix["prog"] == SYS and d[:4] == b"\x02\0\0\0":
            tips.append((keys[ix["acc"][1]], struct.unpack("<Q", d[4:12])[0]))
        elif ix["prog"] == ATAP: atas.append((keys[ix["acc"][1]], keys[ix["acc"][3]], d.hex()))
        elif ix["prog"] == PUMP and d[:8] == BUYD:
            buy = dict(spend=struct.unpack("<Q", d[8:16])[0], min_out=struct.unpack("<Q", d[16:24])[0], tail=d[24:].hex(), acc=[keys[a] for a in ix["acc"]], ix=ix)
        else: other.append(ix["prog"])
    exp_min = max(1, int(1_000_000 / (2.5 * floor_px(r["dev"]))))
    tipnames = [(TIPS.get(a, "UNKNOWN"), a[:8], l) for a, l in tips]
    fan_ok = True
    want = {"jito-bundle": ("jito", 2_000_000), "landx-fra3": ("landx", 1_000_000), "helius": ("helius", 1_000_000), "nozomi": ("nozomi", 1_000_000), "astralane": ("astralane", 1_000_000)}
    need = sorted(want[f] for f in r["fan"] if f in want)
    have = sorted((TIPS.get(a, "UNKNOWN"), l) for a, l in tips)
    exp_cul = 90_000 + (300 * (len(tips) - 2) if len(tips) > 2 else 0)
    age = (r["t_ns"] - bh_first[r["bh"]]) / 1e6 if r["bh"] in bh_first else None
    checks = {"1 sig, signer=payer FRZh": nsig == 1 and keys[0].startswith("FRZh63L6"), "payer FRZh": keys[0] == "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS",
              "buy ix v3": buy is not None, "spend 1e6": buy and buy["spend"] == 1_000_000, "min_out==fill cap": buy and buy["min_out"] == r["min_out"] == exp_min,
              "cu price 30M": cup == 30_000_000, f"cu limit {exp_cul}": cul == exp_cul, "tips = route": have == need, "no other prog": not other,
              "bh == dump": t["bh"] == r["bh"], "mint/bc in buy": buy and buy["acc"][1] == r["mint"] and buy["acc"][5] == r["bc"], "no LUT": t["nlut"] == 0, "<=1232B": len(raw) <= 1232}
    ok = all(bool(v) for v in checks.values()); bad += not ok
    print(f"#{k} {r['mint'][:8]} route={r['route']} client={r['client']} fan={'+'.join(r['fan'])} bytes={len(raw)} cu={cul}/{cup} spend={buy and buy['spend']} min_out={buy and buy['min_out']} (exp {exp_min}, dev {r['dev']/1e9:.3f}) "
          f"tail={buy and buy['tail']} tips={tipnames} atas={[(a[1][:6], a[2]) for a in atas]} bh_age_ms={age if age is None else round(age)} {'OK' if ok else 'FAIL: ' + ','.join(c for c, v in checks.items() if not v)}")
print(f"\ndecoded {len(rows)}  failing structural checks: {bad}")
if rows:
    print("buy ix accounts of the last tx:"); r = rows[-1]; t = parse(base64.b64decode(r["raw"]))
    for ix in t["ixs"]:
        if ix["prog"] == PUMP:
            for i, a in enumerate(ix["acc"]): print(f"   {i:2} {t['keys'][a]}")
# --- simulate the newest N (signature zeroed => cannot be a valid tx anywhere) ---
for r in rows[-nsim:]:
    raw = bytearray(base64.b64decode(r["raw"])); t = parse(bytes(raw))
    raw[1:65] = bytes(64)
    def sim(b):
        res = rpc("simulateTransaction", [base64.b64encode(bytes(b)).decode(), {"encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True, "commitment": "processed"}], tries=2, timeout=20)
        v = (res or {}).get("value") if isinstance(res, dict) else None
        if not v: return f"rpc error {res}", None, []
        return v.get("err"), v.get("unitsConsumed"), v.get("logs") or []
    e1, u1, l1 = sim(raw)
    buy = [ix for ix in t["ixs"] if ix["prog"] == PUMP][0]
    raw2 = bytearray(raw); mo = buy["dofs"] + 16; raw2[mo:mo + 8] = (1).to_bytes(8, "little")
    e2, u2, l2 = sim(raw2)
    tail = lambda L: " | ".join(x[:110] for x in L if "rror" in x or "failed" in x or "AnchorError" in x)[:400]
    print(f"SIM {r['mint'][:8]} as-built: err={e1} cu={u1} {tail(l1)}\n          min_out=1: err={e2} cu={u2} {tail(l2)}")
    if e2 is None: print("          logs ok: " + " | ".join(x[:80] for x in l2 if "Instruction:" in x)[:300])
