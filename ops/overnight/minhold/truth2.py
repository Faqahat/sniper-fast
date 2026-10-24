# On-chain truth that also counts WSOL-funded trades (pump v2 quote = WSOL: the wallet's native SOL does not move, its WSOL account does).
# Per trade tx: if native SOL moved about as much as the event says, use the real SOL change; otherwise (WSOL-funded) use the event's
# curve SOL +/- 1.25% pump fee and minus the tx fee. Plain transfers (no trade event) are reported apart.
import json, sys, glob, os, collections
FEE = 0.0125
for f in sorted(glob.glob("/home/moiz/sniper/ops/overnight/hkq7/ledger24_*.json")):
    w8 = os.path.basename(f)[9:-5]
    if len(sys.argv) > 1 and w8 not in sys.argv[1:]: continue
    try: R = json.load(open(f))
    except Exception: continue
    if not R: continue
    bt = [r["bt"] for r in R if r.get("bt")]; span = (max(bt) - min(bt)) / 86400
    toks = collections.defaultdict(float); native = wsol = 0; net = 0
    for r in R:
        if not (r["ok"] and r["evs"]): continue
        ev = sum((-e["sol"] * (1 + FEE)) if e["buy"] else (e["sol"] * (1 - FEE)) for e in r["evs"])
        gross = sum(e["sol"] for e in r["evs"])
        if gross and abs(r["dsol"]) >= 0.5 * gross: x = r["dsol"]; native += 1
        else: x = ev - (r["fee"] if r["signer"] else 0); wsol += 1
        net += x; toks[r["evs"][0]["mint"]] += x / 1e9
    v = list(toks.values())
    print(f"{w8:9s} span {span*24:4.1f} h | trading net {net/1e9:+8.2f} SOL = {net/1e9/span:+7.1f}/day | tokens {len(v):4d} win {sum(x>0 for x in v)/max(len(v),1):4.0%} | trade txs native {native} / WSOL-funded {wsol}")
