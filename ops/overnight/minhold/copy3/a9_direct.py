#!/usr/bin/env python3
# direct wallet<->creator SOL links in the wallet's own txs (creators of the tokens it traded, the wallet itself excluded), with what
# kind of tx it is (programs, fee payer, both sides' SOL change). Local raw files only. -> out/direct_links.json
import os, sys, json, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
L = lib3.load_launches(); P = [p for p in json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))) if not p.get("nobuy")]
def lines(fn):
    try:
        for l in gzip.open(fn, "rt"): yield l
    except (EOFError, OSError): return
out = {}
for w8, W in lib3.W3.items():
    creators = {L[p["m"]]["creator"] for p in P if p["w"] == w8 and p["m"] in L} - {W}
    hits = []; kinds = collections.Counter()
    for fn in (f"raw/{w8}.jsonl.gz", f"raw/{w8}_ata_a.jsonl.gz", f"raw/{w8}_ata_b.jsonl.gz"):
        if not os.path.exists(fn): continue
        for l in lines(fn):
            try: t = json.loads(l)
            except Exception: continue
            msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
            keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
            if W not in keys: continue
            hit = set(keys) & creators
            if not hit: continue
            pre, post = t["meta"]["preBalances"], t["meta"]["postBalances"]; wi = keys.index(W)
            for c in hit:
                ci = keys.index(c)
                if ci >= len(post) or post[ci] == pre[ci]: continue
                progs = [keys[ix["programIdIndex"]][:8] for ix in msg["instructions"]]
                logs = " ".join(t["meta"].get("logMessages") or [])
                ins = [x.split("Instruction: ")[1].split()[0] for x in (t["meta"].get("logMessages") or []) if "Instruction: " in x][:6]
                h = dict(sig=t["sig"], t=lib3.pkt(t.get("blockTime") or 0), payer=keys[0][:8], w_signer=W in keys[:msg["header"]["numRequiredSignatures"]], creator=c[:8],
                         creator_dsol=(post[ci] - pre[ci]) / 1e9, wallet_dsol=(post[wi] - pre[wi]) / 1e9, progs=progs, ins=ins, nkeys=len(keys))
                hits.append(h); kinds[(h["payer"], tuple(ins[:3]))] += 1
    out[w8] = dict(creators=len(creators), n=len(hits), kinds=[[list(k), v] for k, v in kinds.most_common(6)], sample=hits[:6],
                   wallet_signed=sum(1 for h in hits if h["w_signer"]))
    print(f"\n## {w8}: creators (excl. itself) {len(creators)} | txs where a creator's SOL moves and the wallet is in the tx: {len(hits)} (wallet signed {out[w8]['wallet_signed']})")
    for k, v in kinds.most_common(6): print("   ", v, k)
    for h in hits[:3]: print("   ", h)
json.dump(out, open(os.path.join(lib3.HERE, "out/direct_links.json"), "w"), indent=1)
