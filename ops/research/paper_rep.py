# ZERO-COST paper tally of the creator-reputation trigger (REP, FILTERS2.md) on the live paper engine's launches.
# Reuses the paper_c6 loop's files READ-ONLY (launches_ready.json, leaders.json, rec/ -- no RPC, no ssh, nothing written
# there). History seed = filters2_rows.json (every watched launch up to 10-21 12:37 UTC with its modelled S+2 PnL). Each
# newer watched launch is priced with filters.py's unchanged model and judged ONLY by the same creator's launches that
# ended >= LAG slots before it (~2 min: time to settle + price), then joins the history.
#   REP  = the creator's earlier launches are net positive on the model   -> would fire (extra trigger)
#   bad  = earlier launches net zero/negative                             -> skip for wider triggers
# Prints one line per new REP launch + running totals; tallies in <own dir>/rep_state.json (promotion rule in FILTERS2.md:
# >= +0.03 SOL per REP launch over >= 60 REP launches, +20 ms column positive).
# usage: python3 paper_rep.py <paper_c6 work dir (read-only)> <own work dir> <tipmap.json>
import sys, os, json, shutil, collections

SRC, WORK, TIPMAP = sys.argv[1], sys.argv[2], sys.argv[3]
HERE = os.path.dirname(os.path.abspath(__file__))
LAG = 550                                                       # slots (~2 min at ~217 ms) before a result counts
os.makedirs(WORK, exist_ok=True)
for f in ("launches_ready.json", "leaders.json"):               # private copies (the paper_c6 loop rewrites its files)
    shutil.copyfile(os.path.join(SRC, f), os.path.join(WORK, f))
    try: json.load(open(os.path.join(WORK, f)))
    except ValueError: sys.exit(0)                              # caught mid-write: try again next run
STATE = os.path.join(WORK, "rep_state.json")
src = open(os.path.join(HERE, "filters.py")).read()
src = src.replace('GROUPS = {"A": ["dry1h", "run1"], "B": ["cov", "alt", "cad", "edge1", "latest", "edge2", "edge3", "edge5", "night"], "C": ["morning"]}', 'GROUPS = {"P": ["paper"]}')
src = src.split('json.dump(dict(rows=rows')[0]
sys.argv = ["filters.py", os.path.join(WORK, "launches_ready.json"), os.path.join(SRC, "rec"), os.path.join(WORK, "leaders.json"), TIPMAP, os.path.join(WORK, "out")]
ns = {"__name__": "filters_paper"}
exec(compile(src, "filters.py", "exec"), ns)
L = {(x["S"], x["mint"]): x for x in json.load(open(os.path.join(WORK, "launches_ready.json")))["launches"]}
seed = json.load(open(os.path.join(HERE, "filters2_rows.json")))["rows"]
SEED_MAX = max(r["S"] for r in seed)
sys.path.insert(0, HERE)
from f2_load import market                                      # model-free market response of a launch (S..S+2)
hist = collections.defaultdict(list)                            # creator -> [(S, p2, price ratio at end of S+2)]
for r in sorted(seed, key=lambda r: r["S"]): hist[r["creator"]].append((r["S"], r["p2"], r.get("mkt2", 1.0)))
new = sorted((r for r in ns["rows"] if r["S"] > SEED_MAX), key=lambda r: r["S"])
lun = lambda r: r["tipc"] == "lunar"
early = lambda r: r["create_ms"] is not None and r["create_ms"] <= 150
R2 = lambda r: lun(r) and 3 <= r["gsol"] <= 5 and early(r)
st = json.load(open(STATE)) if os.path.exists(STATE) else {"done": [], "rep": [0, 0.0, 0.0], "rep_added": [0, 0.0, 0.0], "r2": [0, 0.0, 0.0],
                                                           "bad": [0, 0.0, 0.0], "first": [0, 0.0, 0.0], "mf": [0, 0.0, 0.0]}
for r in new:
    c = L[(r["S"], r["mint"])]["creator"]
    hh = [(p, m) for s, p, m in hist[c] if s <= r["S"] - LAG]
    h = [p for p, _ in hh]
    try: mk = market(json.load(open(os.path.join(SRC, "rec", r["mint"] + ".json")))).get("mkt2", 1.0)
    except Exception: mk = 1.0
    k = f"{r['S']}:{r['mint']}"
    if k not in st["done"]:
        st["done"].append(k)
        cls = "first" if not h else ("rep" if sum(h) > 0 else "bad")
        keys = [cls] + (["rep_added"] if cls == "rep" and not R2(r) else []) + (["r2"] if R2(r) else []) + (["mf"] if hh and hh[-1][1] >= 1.1 else [])
        for key in keys:
            st[key][0] += 1; st[key][1] += r["p2"]; st[key][2] += r["pp2"]
        if cls == "rep":
            t = st["rep"]
            print(f"PAPER-REP {r['mint'][:8]} creator {c[:6]} history {len(h)} launches {sum(h):+.3f} | {'RULE#2' if R2(r) else 'ADDED '} {r['cls']:8} "
                  f"tip={r['tipc']:13} bundle {r['gsol']:.2f} {'REFUSED' if r['refused'] else 'fill %.2fx' % r['at_px']}: {r['p2']:+.3f} SOL "
                  f"(20 ms slower {r['pp2']:+.3f}) | REP {t[0]} {t[1]:+.3f} ({t[1] / t[0]:+.3f}/launch)", flush=True)
    hist[c].append((r["S"], r["p2"], mk))
json.dump(st, open(STATE, "w"))
f = lambda key: f"{st[key][0]} launches {st[key][1]:+.3f} SOL ({(st[key][1] / st[key][0]) if st[key][0] else 0:+.3f}/launch, 20 ms slower {(st[key][2] / st[key][0]) if st[key][0] else 0:+.3f})"
print(f"PAPER-REP-SUMMARY new launches since the seed: {len(new)} | REP {f('rep')} | REP outside rule #2 {f('rep_added')} | rule #2 {f('r2')} | "
      f"bad history {f('bad')} | first-time {f('first')} | model-free (last launch >= 1.1x) {f('mf')} | promote if REP >= +0.03/launch over >= 60", flush=True)
