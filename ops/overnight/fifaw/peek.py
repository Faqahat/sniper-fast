#!/usr/bin/env python3
# READ-ONLY, offline: print the anatomy of cached txs (by sig prefix or index filters)
import sys, os, json, glob, base64
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"
TIPS = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big"); return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def show(t, logs=True):
    m = t["transaction"]["message"]; meta = t["meta"]
    keys = [k["pubkey"] for k in m["accountKeys"]]; signers = [k["pubkey"] for k in m["accountKeys"] if k.get("signer")]
    print(f"sig {t['transaction']['signatures'][0]} slot {t['slot']} bt {t.get('blockTime')} v{t.get('version')} err {meta.get('err')} fee {meta['fee']} cu {meta.get('computeUnitsConsumed')} signers {len(signers)} {[s[:6] for s in signers]} bh {m.get('recentBlockhash','')[:10]}")
    for n, ix in enumerate(m["instructions"]):
        pid = ix.get("programId"); p = ix.get("parsed")
        if p:
            inf = p.get("info") if isinstance(p, dict) else p
            extra = ""
            if isinstance(inf, dict) and inf.get("destination") in TIPS: extra = f"  <-- TIP {TIPS[inf['destination']]}"
            print(f"  #{n} {pid[:10]} {p.get('type') if isinstance(p, dict) else ''} {json.dumps(inf)[:260]}{extra}")
        else:
            d = b58d(ix.get("data", "")) if ix.get("data") else b""
            print(f"  #{n} {pid} data[{len(d)}]={d[:24].hex()} accts={len(ix.get('accounts', []))} {[a[:6] for a in ix.get('accounts', [])][:24]}")
    inn = meta.get("innerInstructions") or []
    for g in inn:
        ps = []
        for ix in g["instructions"]:
            p = ix.get("parsed"); ps.append((ix.get("programId") or "")[:6] + ("/" + p.get("type") if isinstance(p, dict) else ""))
        print(f"   inner of #{g['index']}: {ps}")
    pre = {b["accountIndex"]: b for b in meta.get("preTokenBalances") or []}; post = {b["accountIndex"]: b for b in meta.get("postTokenBalances") or []}
    for ai in sorted(set(pre) | set(post)):
        b = post.get(ai) or pre.get(ai)
        a0 = float(((pre.get(ai) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0); a1 = float(((post.get(ai) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0)
        if a0 != a1: print(f"   tok {b['mint'][:8]} owner {str(b.get('owner'))[:8]} {a0:.2f} -> {a1:.2f}")
    i = keys.index(W) if W in keys else None
    if i is not None: print(f"   W sol {(meta['postBalances'][i]-meta['preBalances'][i])/1e9:+.6f}")
    if logs:
        for l in (meta.get("logMessages") or [])[:60]:
            if "Program data" in l: continue
            print("   |", l[:200])
if __name__ == "__main__":
    for s in sys.argv[1:]:
        for f in glob.glob(f"txc_FiFawH/{s}*.json")[:1]: show(json.load(open(f)))
        print()
