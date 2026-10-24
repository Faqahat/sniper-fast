# Would the followers right after us still have filled? Decode each follower buy's slippage limit (pump instruction args) and test it
# against the curve after OUR 1 / 1.5 SOL buy at +50 ms. Then the realistic PnL path keeping only followers whose limit still passes.
import json, os, time, urllib.request, base64
exec(open("fcrv2.py").read().split("for B in (1.0, 1.5):")[0])
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
def dec58(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def limits(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    m = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = m["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    ixs = list(m["instructions"]) + [i for g in t["meta"].get("innerInstructions") or [] for i in g["instructions"]]
    for ix in ixs:
        if keys[ix["programIdIndex"]] == PUMP:
            d = dec58(ix["data"])
            if len(d) >= 24 and M in [keys[a] for a in ix["accounts"]]: return d[:8].hex(), U8(d, 8), U8(d, 16)
    return None
foll = [t for t in tr[k0 + 1:] if t["buy"] and ms(t) - t0 <= 1300 and t["user"] not in G]
LIM = {}
for t in foll: LIM[t["sig"]] = limits(t["sig"]); time.sleep(0.3)
for t in foll: print(f"  {ms(t) - t0:+6.0f} ms {t['user'][:6]} buy {qin(t):6.3f} SOL eq | tokens got {t['tok'] / 1e6:12.0f}M | ix args {LIM[t['sig']]}")
for B in (1.0, 1.5):
    kf = k0
    while kf + 1 < len(tr) and ms(tr[kf + 1]) - t0 <= 50: kf += 1
    vt = tr[kf]["vtok"]; X = B / (1 + FEE); vt2 = u / (u / vt + X); q = vt - vt2; vt = vt2; fill = t0 + 50
    path = [(fill, (u / vt - u / (vt + q)) * (1 - FEE))]; dropped = []
    for t in tr[kf + 1:]:
        if t["buy"]:
            lim = LIM.get(t["sig"])
            if lim:
                tokens_now = vt - u / (u / vt + qin(t))
                # args: (amount, limit). If amount looks like a token amount (== tokens got) the limit is max quote in; else min tokens out
                a1, a2 = lim[1], lim[2]
                if abs(a1 - t["tok"]) / max(t["tok"], 1) < 0.02:      # buy exact tokens, a2 = max quote in (raw quote units unknown) -> keep
                    pass
                elif tokens_now < a2: dropped.append(t["user"][:6]); continue
            vt = u / (u / vt + qin(t))
        else: vt = vt + t["tok"]
        path.append((ms(t), (u / vt - u / (vt + q)) * (1 - FEE)))
    at = lambda sec: [v for m_, v in path if m_ - fill <= sec * 1000][-1]
    print(f"\nREALISTIC, {B} SOL at +50 ms: followers that would FAIL because of our buy: {dropped or 'none'}")
    print("   PnL if we sell after: " + " | ".join(f"{s}s {at(s) - B - 2 * TX:+.3f}" for s in (0.5, 1, 2, 3, 5, 10, 30, 60)))
