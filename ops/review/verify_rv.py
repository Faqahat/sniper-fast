# REVIEW (independent) READ-ONLY verifier: every engine decision in a paper/dry log vs the chain.
# On-chain PREREG_v2 rule #2 (+ base filter):
#   host not a bot launchpad; true dev (TradeEvent buys of the mint in the create tx) 0.5..8 SOL; create_v2; SOL quote
#   (no quote-token balance other than WSOL/the mint, create ix acct 16 = SOL/WSOL); glued bundle (unbroken run of
#   successful buys of the mint right after the create, leader order) >= 1 tx and 3..5 SOL (TradeEvent sol);
#   the create tx has a top-level System transfer to a non-signer "moon..." account (Lunar tip; also noted: is it the largest).
import sys, re, json, base64, hashlib
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, b58dec, PUMP, SYS
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
WSOL = "So11111111111111111111111111111111111111112"
SOLQ = "11111111111111111111111111111111"
CV2 = hashlib.sha256(b"global:create_v2").digest()[:8]
log = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "all"
dec = {}   # mint -> dict(slot, engine verdict, reason, eng bundle)
for l in open(log, errors="replace"):
    m = re.search(r"RACE decide slot=(\d+) mint=(\w+) .*?bundle_n=(\d+) bundle_sol=([\d.]+) .*pass=(\w+)", l)
    if m:
        dec[m.group(2)] = dict(slot=int(m.group(1)), eng="FIRE" if m.group(5) == "true" else "REJ", why="bundle", en=int(m.group(3)), es=float(m.group(4)))
        continue
    m = re.search(r"RACE reject-static slot=(\d+) mint=(\w+)", l)
    if m:
        dec[m.group(2)] = dict(slot=int(m.group(1)), eng="REJ", why="static(tip)")
        continue
    m = re.search(r"DETECT feed=\S+ first=1 .*slot=(\d+) .*mint=(\w+) kind=(\w+) .*dev=(\d+) .*verdict=(skip_\w+)", l)
    if m and m.group(2) not in dec:
        dec[m.group(2)] = dict(slot=int(m.group(1)), eng="REJ", why=m.group(5), edev=int(m.group(4)))
fires_log = set()
for l in open(log, errors="replace"):
    m = re.search(r"(?:PAPER launch #\d+|  FIRE) slot=(\d+) mint=(\w+)", l)
    if m: fires_log.add(m.group(2))
print(f"log {log}: decisions {len(dec)}  engine FIRE {sum(1 for d in dec.values() if d['eng']=='FIRE')}  fire lines {len(fires_log)}")
for mnt in fires_log:
    if mnt not in dec or dec[mnt]["eng"] != "FIRE": print(f"  !! fire line without a pass decision: {mnt}")
sel = list(dec.items())
if mode == "sample":
    fires = [x for x in sel if x[1]["eng"] == "FIRE"]
    rej_r = [x for x in sel if x[1]["eng"] == "REJ" and x[1]["why"] in ("bundle", "static(tip)")]
    rej_b = [x for x in sel if x[1]["eng"] == "REJ" and x[1]["why"].startswith("skip")]
    sel = fires + rej_r + rej_b[:40]
def chain(item):
    mint, d = item
    blk = get_block(d["slot"])
    if not (isinstance(blk, dict) and "transactions" in blk): return mint, d, None
    txs = [t for t in blk["transactions"] if not is_vote(t)]
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        tr, cr = events(meta.get("logMessages"))
        c = [x for x in cr if x["mint"] == mint]
        if not c: continue
        msg = t["transaction"]["message"]
        la = meta.get("loadedAddresses") or {}
        keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        nsig = msg["header"]["numRequiredSignatures"]
        dev = sum(e["sol"] for e in tr if e["mint"] == mint and e["buy"]) / 1e9
        gsol, glued = 0.0, 0
        for t2 in txs[i + 1:]:
            m2 = t2.get("meta") or {}
            tr2, _ = events(m2.get("logMessages"))
            b = [e for e in tr2 if e["mint"] == mint and e["buy"]]
            if m2.get("err") is None and b:
                glued += 1; gsol += sum(e["sol"] for e in b) / 1e9
            else: break
        transfers = []
        q16 = None
        for ix in msg["instructions"]:
            pid = keys[ix["programIdIndex"]]
            raw = b58dec(ix["data"])
            if pid == SYS and len(raw) >= 12 and int.from_bytes(raw[:4], "little") == 2:
                acc = ix["accounts"]
                if len(acc) >= 2 and acc[1] >= nsig: transfers.append((int.from_bytes(raw[4:12], "little"), keys[acc[1]]))
            if pid == PUMP and raw[:8] == CV2 and len(ix["accounts"]) > 16: q16 = keys[ix["accounts"][16]]
        moon = [x for x in transfers if x[1].startswith("moon")]
        largest = max(transfers)[1] if transfers else None
        qmints = {b["mint"] for b in (meta.get("postTokenBalances") or [])} - {mint, WSOL}
        host = c[0]["uri"].split("://")[-1].split("/")[0]
        v2 = any("Instruction: CreateV2" in x for x in (meta.get("logMessages") or []))
        res = dict(host=host, dev=dev, glued=glued, gsol=gsol, moon=bool(moon), moon_amt=sum(x[0] for x in moon) / 1e9,
                   largest_moon=bool(largest and largest.startswith("moon")), v2=v2, solq=(not qmints) and q16 in (None, SOLQ, WSOL), q16=q16, qmints=list(qmints)[:2],
                   err=meta.get("err") is not None)
        return mint, d, res
    return mint, d, None
with ThreadPoolExecutor(6) as ex: out = list(ex.map(chain, sel))
mis = unv = 0; bord = 0
rows = []
lit_only = []
for mint, d, r in sorted(out, key=lambda x: (x[1]["eng"] != "FIRE", x[1]["why"])):
    if r is None:
        unv += 1; print(f"  {mint[:10]} {d['eng']:4} {d['why']:12} UNVERIFIABLE (create not found)"); continue
    ch = {"host": not (r["host"] in BOT or r["host"].endswith(".trycloudflare.com")), "dev0.5-8": 0.5 <= r["dev"] <= 8.0,
          "v2": r["v2"], "solq": r["solq"], "bundle>=1": r["glued"] >= 1, "bsol3-5": 3.0 <= r["gsol"] <= 5.0, "moonL": r["largest_moon"]}
    any_moon_pass = all(v for k, v in ch.items() if k != "moonL") and r["moon"]
    chain_pass = all(ch.values())
    near = (abs(r["gsol"] - 3) < 0.03 or abs(r["gsol"] - 5) < 0.05) or abs(r["dev"] - 0.5) < 0.01 or abs(r["dev"] - 8) < 0.08
    ok = (chain_pass == (d["eng"] == "FIRE"))
    if not ok:
        if near: bord += 1
        else: mis += 1
    fail = ",".join(k for k, v in ch.items() if not v)
    if any_moon_pass and not chain_pass: lit_only.append(mint)
    eng = f"eng_b={d.get('en','-')}/{d.get('es','-')}" if "es" in d else (f"eng_dev={d['edev']/1e9:.2f}" if "edev" in d else "")
    print(f"  {mint[:10]} {d['eng']:4} {d['why']:12} chain={'PASS' if chain_pass else 'fail'} {'OK ' if ok else ('BORDER' if near else 'MISMATCH')} dev={r['dev']:.3f} "
          f"glued={r['glued']}/{r['gsol']:.3f} moon={int(r['moon'])}{'(L)' if r['largest_moon'] else ''} {r['moon_amt']:.4f} v2={int(r['v2'])} solq={int(r['solq'])} host={r['host'][:22]} {eng} {('fails:' + fail) if fail else ''}")
print(f"\nchecked {len(out) - unv}  unverifiable {unv}  MISMATCHES {mis}  borderline-disagreements {bord}")
print(f"launches passing ONLY under the literal 'any System transfer to moon...' reading (moon tip not the largest transfer): {len(lit_only)}")
print(f"engine FIRE checked: {sum(1 for _, d, r in out if r and d['eng']=='FIRE')}   engine REJ checked: {sum(1 for _, d, r in out if r and d['eng']=='REJ')}")
