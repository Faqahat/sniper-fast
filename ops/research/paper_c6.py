# ZERO-COST paper test of the wider filter C6 ("any create tip, glued bundle 2-5 SOL, create <= 150 ms") next to rule #2,
# on the LIVE paper engine's log (junk-fanout dry run). Every launch the engine watched (base filter + close leader) is
# recorded from the chain once its blocks are settled and priced with filters.py's model (measured landing per leader
# class, real cap / fees / tips, sell at the end of S+2). Prints one line per new C6 or rule #2 launch + running totals,
# and keeps the "added only" (C6 minus rule #2) tally that decides promotion: > +0.02 SOL per added launch over >= ~100.
# usage: python3 paper_c6.py <paper log copy> <work dir> <tipmap.json>
import sys, os, json, subprocess, urllib.request

LOG, WORK, TIPMAP = sys.argv[1], sys.argv[2], sys.argv[3]
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(WORK, "rec"), exist_ok=True); os.makedirs(os.path.join(WORK, "blk"), exist_ok=True)
STATE = os.path.join(WORK, "state.json")
py = [sys.executable, "-I"]


def cur_slot():
    for ep in ("https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(ep, data=b'{"jsonrpc":"2.0","id":1,"method":"getSlot"}', headers={"content-type": "application/json"}), timeout=20))["result"]
        except Exception:
            pass
    return None


q = lambda *a: subprocess.run(list(a), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1500)
LJ = os.path.join(WORK, "launches.json"); LJR = os.path.join(WORK, "launches_ready.json"); LD = os.path.join(WORK, "leaders.json")
q(*py, os.path.join(HERE, "parse_logs.py"), LJ, f"paper={LOG}")
if not os.path.exists(LJ): sys.exit(0)
D = json.load(open(LJ)); now = cur_slot()
if not now: sys.exit(0)
D["launches"] = [r for r in D["launches"] if r["S"] < now - 40]          # blocks S..S+2 settled (never cache an unsettled slot)
if not D["launches"]: sys.exit(0)
json.dump(D, open(LJR, "w"))
q(*py, os.path.join(HERE, "leaders.py"), LJR, LD)
subprocess.run(py + [os.path.join(HERE, "rec_launches.py"), LJR, os.path.join(WORK, "rec"), os.path.join(WORK, "blk")], env=dict(os.environ, K="2", THREADS="3"),
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1500)
# price every recorded launch with filters.py (exec'd with the paper log as the only group)
src = open(os.path.join(HERE, "filters.py")).read()
src = src.replace('GROUPS = {"A": ["dry1h", "run1"], "B": ["cov", "alt", "cad", "edge1", "latest", "edge2", "edge3", "edge5", "night"], "C": ["morning"]}', 'GROUPS = {"P": ["paper"]}')
src = src.split('json.dump(dict(rows=rows')[0]
sys.argv = ["filters.py", LJR, os.path.join(WORK, "rec"), LD, TIPMAP, os.path.join(WORK, "out")]
ns = {"__name__": "filters_paper"}
exec(compile(src, "filters.py", "exec"), ns)
rows = ns["rows"]
lun = lambda r: r["tipc"] == "lunar"
early = lambda r: r["create_ms"] is not None and r["create_ms"] <= 150
R2 = lambda r: lun(r) and 3 <= r["gsol"] <= 5 and early(r)
C6 = lambda r: early(r) and 2 <= r["gsol"] <= 5
st = json.load(open(STATE)) if os.path.exists(STATE) else {"done": [], "r2": [0, 0.0, 0.0], "c6": [0, 0.0, 0.0], "add": [0, 0.0, 0.0]}
new = 0
for r in sorted(rows, key=lambda r: r["S"]):
    k = f"{r['S']}:{r['mint']}"
    if k in st["done"] or not C6(r): continue
    st["done"].append(k); new += 1
    is2 = R2(r)
    for key, on in (("r2", is2), ("c6", True), ("add", not is2)):
        if on: st[key][0] += 1; st[key][1] += r["p2"]; st[key][2] += r["pp2"]
    a = st["add"]
    print(f"PAPER-C6 {r['mint'][:8]} {'RULE#2' if is2 else 'ADDED '} {r['cls']:8} tip={r['tipc']:13} bundle {r['gsol']:.2f} SOL "
          f"{'REFUSED' if r['refused'] else 'fill %.2fx' % r['at_px']}: {r['p2']:+.3f} SOL (if 20 ms slower {r['pp2']:+.3f}) | "
          f"rule#2 {st['r2'][0]} {st['r2'][1]:+.3f} | C6 {st['c6'][0]} {st['c6'][1]:+.3f} | added {a[0]} {a[1]:+.3f} "
          f"({(a[1] / a[0]) if a[0] else 0:+.3f}/launch, slower {(a[2] / a[0]) if a[0] else 0:+.3f})", flush=True)
json.dump(st, open(STATE, "w"))
if new:
    a, c, r2 = st["add"], st["c6"], st["r2"]
    print(f"PAPER-C6-SUMMARY +{new} new | rule#2 {r2[0]} launches {r2[1]:+.3f} SOL | wider (2-5 SOL, any tip) {c[0]} {c[1]:+.3f} | "
          f"ADDED only {a[0]} launches {a[1]:+.3f} SOL = {(a[1] / a[0]) if a[0] else 0:+.3f}/launch (20 ms slower {(a[2] / a[0]) if a[0] else 0:+.3f}); "
          f"promote if > +0.020/launch over ~100", flush=True)
