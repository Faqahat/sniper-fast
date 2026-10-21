# ZERO-COST paper trading of the live engine (junk-fanout dry run = Run 2's exact detection, gates, routing): for every
# launch the engine FIRED on, once its blocks are settled, place our buy at the landing time we measured live for that
# leader type and route, and price it on the real block: real price cap, real tips (from the FAST-FIRE line), priority
# fee, pump fees, sell at the end of S+2 (Run 2's --hold-slots 2; S+1 shown too). Prints one row per new paper trade.
# usage: python3 paper_live.py <dry log copy> <rec dir> <state json>     env: PESS=20 (ms added in the pessimistic column)
import sys, os, re, json, time, subprocess, urllib.request

LOG, REC, STATE = sys.argv[1], sys.argv[2], sys.argv[3]
HERE = os.path.dirname(os.path.abspath(__file__))
PESS = float(os.environ.get("PESS", "20"))
# measured landing (ms after the create) by leader class, Run 2 routes (FRZ, 2026-10-21): BAM real buy 17.6; Jito-client
# buy-shaped 17.4/51.6 (+ edge 9-33); Harmonic one route 26.6-33.6; Harmonic multi-route (last-slot union) 96-148
T_BY = {"bam": 20.0, "jito": 35.0, "harmonic": 32.0, "harmonic_union": 120.0, "fd": 20.0, "other": 35.0}


def cls(client, route):
    if client.startswith("Harmonic"): return "harmonic_union" if "+" in route else "harmonic"
    if client in ("AgaveBam", "FireBAM"): return "bam"
    if client == "JitoLabs": return "jito"
    if client in ("Firedancer", "Frankendancer"): return "fd"
    return "other"


def cur_slot():
    for ep in ("https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(ep, data=b'{"jsonrpc":"2.0","id":1,"method":"getSlot"}', headers={"content-type": "application/json"}), timeout=20))["result"]
        except Exception:
            pass
    return None


txt = open(LOG, errors="replace").read()
fires = {}
for m in re.finditer(r"^\s+FIRE slot=(\d+) mint=(\w+).*?fee_prio=(\d+)", txt, re.M):
    fires[(int(m.group(1)), m.group(2))] = dict(prio=int(m.group(3)) / 1e9)
for m in re.finditer(r"FAST-FIRE tag=\d+ slot=(\d+) mint=(\w+).*?route:(\S+) leader=(\w+) client=(\w+) .*?tips=(\d+)", txt):
    k = (int(m.group(1)), m.group(2))
    if k in fires: fires[k].update(route=m.group(3), leader=m.group(4), client=m.group(5), tips=int(m.group(6)) / 1e9)
for m in re.finditer(r"GATE-CREATE-MS slot=(\d+) mint=(\w+) create_ms=([\d.]+)", txt):
    k = (int(m.group(1)), m.group(2))
    if k in fires: fires[k]["create_ms"] = float(m.group(3))
state = json.load(open(STATE)) if os.path.exists(STATE) else {"done": {}, "total": 0.0, "total_pess": 0.0}
now = cur_slot()
ready = {k: v for k, v in fires.items() if f"{k[0]}:{k[1]}" not in state["done"] and now and k[0] < now - 12 and "client" in v}
if not ready: sys.exit(0)
# record the ready launches (blocks S..S+3) with the FIRE-lines selector
tmp = STATE + ".ready.log"
with open(tmp, "w") as f:
    for line in txt.splitlines():
        if any(f"slot={s}" in line and m in line for s, m in ready): f.write(line + "\n")
subprocess.run([sys.executable, "-I", os.path.join(HERE, "mini_record.py"), REC, tmp], env=dict(os.environ, FIRELINES="1", K="3"),
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
# the replay model (sim_land.py's run()), outs read from the full log
sys.argv = ["sim_land.py", REC, LOG]
os.environ["EXITS"] = "1,2"
exec(open(os.path.join(HERE, "sim_land.py")).read().split("\nL = []")[0])
for (S, mint), v in sorted(ready.items()):
    p = os.path.join(REC, f"{mint}.json")
    if not os.path.exists(p): continue
    r = json.load(open(p)); r["create_ms"] = v.get("create_ms"); r["slot_ms"] = 217.4
    c = cls(v["client"], v["route"]); T = T_BY[c]
    globals()["PRIO"] = v["prio"]; globals()["TIPS"] = v["tips"]
    o, op = run(r, T), run(r, T + PESS)
    if not o: continue
    ob = sorted([x for x in outs.get((S, mint), []) if x[2] == "1"], key=lambda x: x[0])
    first = f"{ob[0][0]:.0f} ms {ob[0][3]} {ob[0][1]:.2f}" if ob else "none"
    state["done"][f"{S}:{mint}"] = dict(pnl2=o["pnl"][2], pnl1=o["pnl"][1], pess2=op["pnl"][2], cls=c, T=T, refused=o["refused"])
    state["total"] += o["pnl"][2]; state["total_pess"] += op["pnl"][2]
    n = len(state["done"])
    print(f"PAPER #{n} {time.strftime('%H:%M', time.gmtime())} {mint[:8]} {v['client']} {v['route']} land {T:.0f}ms (first peer: {first}) -> "
          f"{'REFUSED by cap' if o['refused'] else 'filled at %.2fx' % o['at_px']}: PnL {o['pnl'][2]:+.3f} SOL (S+1 {o['pnl'][1]:+.3f}; "
          f"if {PESS:.0f} ms slower {op['pnl'][2]:+.3f}) | total {state['total']:+.3f} SOL (slower {state['total_pess']:+.3f}) after {n}", flush=True)
json.dump(state, open(STATE, "w"))
os.remove(tmp)
