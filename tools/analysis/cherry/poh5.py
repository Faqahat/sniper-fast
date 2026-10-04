#!/usr/bin/env python3
"""Data late or post-send path? Every transaction placed on its leader's PoH clock (poh.log: all entries-feed txs), so
for each gap: trigger -> winner ms and trigger -> ours ms on the same clock, plus each leader's distance from Cherry
(L = RTT/2). Winners come from the engine's takers (opportunities.jsonl) and the block check (takers file)."""
import json, subprocess, collections, concurrent.futures as cf, types, sys
_ns = {}
exec(open("/root/arb-lab/takers.py").read().split('out = open("/root/arb-lab/runs/"')[0], _ns)
T = types.SimpleNamespace(**_ns)
RUN = sys.argv[1]; TK = sys.argv[2] if len(sys.argv) > 2 else None
B = f"/root/arb-lab/runs/{RUN}/"
q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None

log = {}
for line in open(B + "poh.log"):
    s8, slot, ms = line.split()
    log.setdefault(s8, (int(slot), float(ms)))
def at(sig): return log.get(T.b58d(sig)[:8].hex()) if sig else None
def after(x, y): return (x[0] - y[0]) * 400 + x[1] - y[1]
print(f"poh.log: {len(log)} transactions on the leader clock")

a = {x["attempt"]: x for x in map(json.loads, open(B + "attempts.jsonl"))}
o = [json.loads(l) for l in open(B + "outcomes.jsonl")]
L_ = [x for x in o if x.get("landed")]
print(f"RUN {RUN}: trades {len(a)}, landed {len(L_)}, wins {sum(1 for x in L_ if x.get('ok'))}, landed by {dict(collections.Counter(x['landed'] for x in L_))},"
      f" fees {sum(x['fee_lamports'] for x in L_)} (per miss median {q([x['fee_lamports'] for x in L_ if not x.get('ok')], .5)})")

# winners: (trigger slot, ms after trigger, source)
win = []
for x in map(json.loads, open(B + "opportunities.jsonl")):
    t = (x.get("taker") or {}).get("sig")
    tp, wp = at(x["trigger"]), at(t)
    if tp and wp: win.append((tp[0], after(wp, tp), "engine"))
if TK:
    for r in map(json.loads, open(f"/root/arb-lab/runs/{TK}")):
        for k in r["takers"][:1]:
            tp, wp = at(a[r["attempt"]]["trigger"]) if r["attempt"] in a else None, at(k["sig"])
            if tp and wp: win.append((tp[0], after(wp, tp), "block"))
ours = []
for x in L_:
    tp, op = at(a[x["attempt"]]["trigger"]), at(x["sig"])
    if tp and op: ours.append((tp[0], after(op, tp)))
w = [v for _, v, _ in win]
print(f"WINNERS after the trigger (leader clock): n={len(w)} p10/p50/p90 {q(w,.1)}/{q(w,.5)}/{q(w,.9)} ms; <=1 ms {sum(1 for v in w if v<=1)}, <=5 ms {sum(1 for v in w if v<=5)}, <=10 ms {sum(1 for v in w if v<=10)}")
ov = [v for _, v in ours]
print(f"OURS after the trigger (leader clock):    n={len(ov)} p10/p50/p90 {q(ov,.1)}/{q(ov,.5)}/{q(ov,.9)} ms")

slots = sorted({s for s, *_ in win} | {s for s, _ in ours})
lead = {}
if slots:
    r = T.rpc("getSlotLeaders", [slots[0], slots[-1] - slots[0] + 1])
    if isinstance(r, list): lead = {slots[0] + i: k for i, k in enumerate(r)}
nodes = T.rpc("getClusterNodes", [])
ip = {n["pubkey"]: (n.get("gossip") or "").split(":")[0] for n in nodes} if isinstance(nodes, list) else {}
def ping(h):
    if not h: return None
    try:
        out = subprocess.run(["ping", "-c", "3", "-i", "0.2", "-W", "1", "-q", h], capture_output=True, text=True, timeout=6).stdout
        line = [l for l in out.splitlines() if "min/avg" in l]
        return float(line[0].split("=")[1].split("/")[0]) if line else None
    except Exception: return None
leaders = sorted({lead.get(s) for s in slots if lead.get(s)})
with cf.ThreadPoolExecutor(16) as ex: rtt = dict(zip(leaders, ex.map(lambda k: ping(ip.get(k)), leaders)))
Lof = lambda s: rtt.get(lead.get(s)) / 2 if rtt.get(lead.get(s)) else None
Ls = [v / 2 for v in rtt.values() if v]
print(f"LEADERS: {len(leaders)} over {len(slots)} slots, {len(Ls)} answered ping; one-way L p10/p50/p90 {q(Ls,.1)}/{q(Ls,.5)}/{q(Ls,.9)} ms")
wl = [(v, Lof(s)) for s, v, _ in win if Lof(s) is not None]
if wl:
    before = sum(1 for v, L in wl if v < L)
    reach = sum(1 for v, L in wl if L <= v <= 2 * L + 1.1 + 5)
    print(f"VERDICT winners (n={len(wl)}): before shreds could reach Frankfurt (v < L): {before} ({before*100//len(wl)}%) = DATA/visibility;"
          f" within reach of a shred-reacting bot here (L..2L+6 ms): {reach} ({reach*100//len(wl)}%); later than that: {len(wl)-before-reach}")
ol = [(v, Lof(s)) for s, v in ours if Lof(s) is not None]
if ol:
    extra = [v - 2 * L - 1.1 for v, L in ol]
    print(f"VERDICT ours (n={len(ol)}): {q([v for v,_ in ol],.5)} ms after the trigger vs the physics floor 2L+1.1 = {q([2*L+1.1 for _,L in ol],.5)} ms;"
          f" our send path + leader queue add p10/p50/p90 {q(extra,.1)}/{q(extra,.5)}/{q(extra,.9)} ms")
