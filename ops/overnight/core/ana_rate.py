import sys, json, collections, statistics, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from ana_fwd import rows, table, NAMES
L = rp.load_launches(); A = json.load(open("attempts.json"))
cut = datetime.datetime(2026, 10, 22, 17, 9, tzinfo=datetime.timezone.utc).timestamp()
# attempt RATE per deployer before the cutoff (collector runs only: launches we saw + attempts on them)
la = collections.Counter(); at = collections.defaultdict(collections.Counter)
for m, c in L.items():
    if not c.get("bt") or c["bt"] >= cut: continue
    la[c["user"]] += 1
    for w in A.get(m, {}): at[w][c["user"]] += 1
def rate_list(w, min_rate, min_att=2):
    return {d for d, n in at[w].items() if n >= min_att and n / la[d] >= min_rate}
for w in ("9Sh2fd", "DGmspi", "D24ipY"):
    for mr in (0.2, 0.4):
        S = rate_list(w, mr)
        R = table(f"RATE LIST {w}: deployers with attempt rate >= {mr:.0%} (and >= 2 attempts) before the window -> ALL their launches ({len(S)} deployers)", lambda r, S=S: r["signer"] in S, cfgs=("L75", "L60", "L35"), top=4, min_n=5)
        print(f"      {w} attempted {sum(1 for r in R if w in r['att'])} of {len(R)}")
# within-deployer: attempted vs not attempted launches (test window), list deployers, PnL at L75
print("\n== WITHIN followed deployers (test window): attempted vs skipped launches, L75")
for w in ("9Sh2fd", "DGmspi"):
    deps = {d for d, n in at[w].items() if n >= 2}
    R = [r for r in rows if r["signer"] in deps and "L75" in r["cfg"]]
    for nm in ("hold0.3s", "hold2s", "hold10s", "hold30s", "tp3.0_slNone_c60", "fsell_any"):
        i = NAMES.index(nm)
        a = [r["cfg"]["L75"]["pnl"][i] for r in R if w in r["att"]]; b = [r["cfg"]["L75"]["pnl"][i] for r in R if w not in r["att"]]
        print(f"   {w} {nm:18} attempted n {len(a):3} mean {statistics.mean(a) if a else 0:+.4f} | skipped n {len(b):3} mean {statistics.mean(b) if b else 0:+.4f}")
