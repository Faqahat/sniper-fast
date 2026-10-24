# On-chain truth from ledger24 JSONs: trading net (txs with a pump trade event of the wallet) vs plain transfers, per day.
import json, sys, glob, os, collections, statistics
for f in sorted(glob.glob("/home/moiz/sniper/ops/overnight/hkq7/ledger24_*.json")):
    w8 = os.path.basename(f)[9:-5]
    if len(sys.argv) > 1 and w8 not in sys.argv[1:]: continue
    try: R = json.load(open(f))
    except Exception: continue
    if not R: continue
    bt = [r["bt"] for r in R if r.get("bt")]; span = (max(bt) - min(bt)) / 86400
    tr = [r for r in R if r["ok"] and r["evs"]]; oth = [r for r in R if r["ok"] and not r["evs"]]; bad = [r for r in R if not r["ok"] and r["signer"]]
    toks = collections.defaultdict(float)
    for r in tr: toks[r["evs"][0]["mint"]] += r["dsol"] / 1e9
    v = list(toks.values())
    print(f"{w8:9s} span {span*24:4.1f} h | trading net {sum(r['dsol'] for r in tr)/1e9:+8.2f} SOL = {sum(r['dsol'] for r in tr)/1e9/span:+7.1f}/day | tokens {len(v):4d} win {sum(x>0 for x in v)/max(len(v),1):4.0%} | "
          f"failed {len(bad):5d} ({sum(r['fee'] for r in bad)/1e9:.3f} SOL) | transfers {sum(r['dsol'] for r in oth)/1e9:+8.2f}")
