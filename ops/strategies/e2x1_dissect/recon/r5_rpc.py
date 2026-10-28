#!/usr/bin/env python3
"""recon step 5 (read-only): parse gettx.jsonl (public RPC) into r3-shaped rows (rpc_tx.pkl), spot-check recorded rows against
RPC pre/post balances, and print the boundary balances. Out: rpc_tx.pkl, r5.txt"""
import json, pickle, struct, collections, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r3_decomp import parse as parse_ev, b58, DISC, CPI, RENTS
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
TIP = json.load(open(f"{OUT}/tipmap.json"))
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; CB = "ComputeBudget111111111111111111111111111111"
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + A58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def keys_of(res):
    msg = res["transaction"]["message"]; la = res["meta"].get("loadedAddresses") or {}
    return [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]] + (la.get("writable") or []) + (la.get("readonly") or [])
def to_row(res):
    msg = res["transaction"]["message"]; meta = res["meta"]; keys = keys_of(res)
    hi = keys.index(H) if H in keys else None
    sd_all = {k: meta["postBalances"][j] - meta["preBalances"][j] for j, k in enumerate(keys[:len(meta["preBalances"])])}
    signers = [k["pubkey"] for k in msg["accountKeys"] if isinstance(k, dict) and k.get("signer")]
    own = signers and signers[0] == H; ok = meta["err"] is None
    cup = cul = None; ixn = []; events = []; tips = []; progs = set()
    ins = [(1, x) for x in msg["instructions"]] + [(2, x) for g in meta.get("innerInstructions") or [] for x in g["instructions"]]
    for lvl, x in ins:
        pid = x.get("programId"); progs.add(pid)
        if pid == CB and "data" in x:
            d = b58d(x["data"])
            if d and d[0] == 3: cup = struct.unpack_from("<Q", d, 1)[0]
            if d and d[0] == 2: cul = struct.unpack_from("<I", d, 1)[0]
        if pid == PUMP and lvl == 2 and "data" in x:
            d = b58d(x["data"])
            if d[:8] == CPI and d[8:16] == DISC and len(d) >= 8 + 225:
                e = parse_ev(d[8:])
                if e["user"] == H: events.append(e)
        p = x.get("parsed")
        if isinstance(p, dict):
            if x.get("program") == "system" and p.get("type") == "transfer" and p["info"].get("source") == H and p["info"].get("destination") in TIP:
                tips.append((p["info"]["destination"], int(p["info"]["lamports"])))
    logs = meta.get("logMessages") or []
    for lg in logs:
        if lg.startswith("Program log: Instruction: "): ixn.append(lg.split(": ", 2)[2])
    tb = []
    pre = {(b["mint"], b.get("owner")): int(b["uiTokenAmount"]["amount"]) for b in meta.get("preTokenBalances") or []}
    post = {(b["mint"], b.get("owner")): int(b["uiTokenAmount"]["amount"]) for b in meta.get("postTokenBalances") or []}
    for k in set(pre) | set(post):
        if pre.get(k, 0) != post.get(k, 0): tb.append([k[0], k[1], pre.get(k, 0), post.get(k, 0)])
    sd = sd_all.get(H, 0); tipsum = sum(v for a, v in tips) if ok else 0
    txfee = meta["fee"] if own else 0
    kind = ("third" if not own else "fail" if not ok else "buy" if any(x.startswith("Buy") for x in ixn) else "sell" if any(x.startswith("Sell") for x in ixn) else "other")
    mint = events[0]["mint"] if events else next((m for m, o, a, b in tb if o == H), None)
    r = dict(sig=res["transaction"]["signatures"][0], s=res["slot"], i=res.get("transactionIndex"), bt=res["blockTime"], ok=ok, err=meta["err"], kind=kind, own=bool(own),
             signers=signers, txfee=txfee, cu=meta.get("computeUnitsConsumed"), cup=cup, cul=cul, tips=tipsum, tip_acc=[a for a, v in tips], tip_amt=[v for a, v in tips],
             relay="+".join(sorted(set(TIP.get(a, "?") for a, v in tips))) or "none", progs=sorted(progs), ixn="|".join(ixn), mints=None, sd=sd, nev=len(events),
             mint=mint, events=events, trade=0, sol=0, tok=0, pfee=0, cfee=0, rent_c=0, rent_x=0, other=0, tb=tb, src="rpc",
             pre=meta["preBalances"][hi] if hi is not None else None, post=meta["postBalances"][hi] if hi is not None else None,
             transfers=[(lvl, x["parsed"]["info"].get("source"), x["parsed"]["info"].get("destination"), int(x["parsed"]["info"].get("lamports", 0)))
                        for lvl, x in ins if isinstance(x.get("parsed"), dict) and x.get("program") == "system" and x["parsed"].get("type") == "transfer"])
    if events:
        e = events[0]; r.update(sol=e["sol"], tok=e["tok"], pfee=e["fee"], cfee=e["cfee"], side=("buy" if e["buy"] else "sell"), vsol=e["vsol"], vtok=e["vtok"])
        r["trade"] = sum((-(x["sol"] + x["fee"] + x["cfee"]) if x["buy"] else (x["sol"] - x["fee"] - x["cfee"])) for x in events)
    if own and ok:
        rest = sd - (r["trade"] - txfee - tipsum)
        r["rent_c"] = sum(v for a, v in sd_all.items() if a != H and v in RENTS and a not in dict(tips))
        r["rent_x"] = sum(-v for a, v in sd_all.items() if a != H and -v in RENTS)
        r["other"] = rest + r["rent_c"] - r["rent_x"]
    elif own: r["other"] = sd + txfee
    else: r["other"] = sd
    return r
if __name__ == "__main__":
    G = {}
    for l in open(f"{OUT}/gettx.jsonl"):
        j = json.loads(l)
        if j.get("res"): G[j["sig"]] = (j["why"], j["res"])
    R3 = {r["sig"]: r for r in pickle.load(open(f"{OUT}/tx.pkl", "rb"))}
    rows = {sig: to_row(res) for sig, (why, res) in G.items()}
    pickle.dump([r for r in rows.values()], open(f"{OUT}/rpc_tx.pkl", "wb"))
    L = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); L.append(s)
    un = [rows[s] for s, (w, _) in G.items() if w == "unrec"]
    P("unrecorded fetched:", len(un), collections.Counter((r["kind"], r["ixn"][:50], str(r["err"])[:40]) for r in un).most_common(20))
    for r in un:
        if r["ok"]: P("  ok unrec:", r["sig"][:20], r["kind"], r["bt"], r["sd"], r["ixn"][:60], r["progs"], r["transfers"][:4], "other", r["other"])
    # spot check
    n = bad = 0
    for sig, (w, res) in G.items():
        if sig in R3:
            n += 1; a = R3[sig]; b = rows[sig]
            if a["sd"] != b["sd"] or a["trade"] != b["trade"] or a["tips"] != b["tips"] or a["txfee"] != b["txfee"]:
                bad += 1; P("  MISMATCH", sig[:20], a["sd"], b["sd"], a["trade"], b["trade"], a["tips"], b["tips"])
    P(f"spot-check recorded vs RPC: {n} txs, mismatches {bad}")
    for w in ("bA", "b0", "b1"):
        P(w, [(rows[s]["s"], rows[s]["i"], rows[s]["bt"], rows[s]["pre"], rows[s]["post"]) for s, (ww, _) in sorted(G.items(), key=lambda t: (t[1][1]["slot"], t[1][1].get("transactionIndex") or 0)) if ww == w])
    open(f"{OUT}/r5.txt", "w").write("\n".join(L) + "\n")
