#!/usr/bin/env python3
"""live-run-4: is it the data (we learn of the trigger too late) or our post-send path (we learn in time but arrive
late)? On the leaders' PoH clocks (exact): trigger -> winner ms, trigger -> our tx ms. Plus each slot's leader and
its network distance from Cherry (RTT/2 = L, the least time a shred takes to reach us, and our copy to reach it):
  winner faster than L          -> nobody reacting to shreds in Frankfurt could have done it: DATA (visibility/location)
  our delay - (2L + 1.1 ms)     -> what our send path adds beyond the physics: POST-SEND (relay hops, leader queue)
Read-only (RPC getSlotLeaders / getClusterNodes, ICMP ping)."""
import json, subprocess, collections, statistics as S, concurrent.futures as cf, types, sys
_ns = {}
exec(open("/root/arb-lab/takers.py").read().split('out = open("/root/arb-lab/runs/"')[0], _ns)
T = types.SimpleNamespace(**_ns)
RUN = sys.argv[1] if len(sys.argv) > 1 else "live-run-4"
B = f"/root/arb-lab/runs/{RUN}/"
q = lambda v, p: sorted(v)[min(len(v) - 1, int(len(v) * p))] if v else None

# 1. the run
st = json.loads(open(B + "status.jsonl").readlines()[-1])
a = {x["attempt"]: x for x in map(json.loads, open(B + "attempts.jsonl"))}
o = [json.loads(l) for l in open(B + "outcomes.jsonl")]
L_ = [x for x in o if x.get("landed")]
print(f"RUN {RUN}: trades {len(a)}, landed {len(L_)}, wins {sum(1 for x in L_ if x.get('ok'))}, landed by {dict(collections.Counter(x['landed'] for x in L_))}")
print(f"  fees {sum(x['fee_lamports'] for x in L_)} lamports, per landed miss median {q([x['fee_lamports'] for x in L_ if not x.get('ok')], .5)}; arms {dict(collections.Counter(x['fee_arm'] for x in a.values()))}")
print(f"  engine: { {k: v for k, v in st['counts'].items() if k.startswith('trigger') or k == 'opportunity'} }")
rt = [(x.get("round_trip_on_chain"), x.get("round_trip_predicted")) for x in L_ if x.get("round_trip_on_chain") is not None]
if rt: print(f"  on chain the round trip returned (median) {q([r[0] for r in rt], .5)} vs predicted {q([r[1] for r in rt], .5)} lamports ({len(rt)} legs-ran)")

# 2. PoH delays after the trigger (exact, leader clock)
opp = [json.loads(l) for l in open(B + "opportunities.jsonl")]
win = [(x["slot"], x["poh"]["taker_ms_after_trigger"]) for x in opp if (x.get("poh") or {}).get("taker_ms_after_trigger") is not None]
ours = [(a[x["attempt"]]["slot"], x["poh"]["ours_ms_after_trigger"]) for x in L_ if (x.get("poh") or {}).get("ours_ms_after_trigger") is not None]
print(f"POH (leader clock): opportunities with a trigger position {sum(1 for x in opp if (x.get('poh') or {}).get('trigger'))}/{len(opp)}")
print(f"  WINNERS ran after the trigger: n={len(win)} p10/p50/p90 {q([w[1] for w in win], .1)}/{q([w[1] for w in win], .5)}/{q([w[1] for w in win], .9)} ms; within 1 ms {sum(1 for w in win if w[1] <= 1)}, within 5 ms {sum(1 for w in win if w[1] <= 5)}")
print(f"  OURS ran after the trigger:    n={len(ours)} p10/p50/p90 {q([w[1] for w in ours], .1)}/{q([w[1] for w in ours], .5)}/{q([w[1] for w in ours], .9)} ms")

# 3. leaders and their distance
slots = sorted({s for s, _ in win} | {s for s, _ in ours})
if not slots: sys.exit(0)
lead = {}
lo = slots[0]
r = T.rpc("getSlotLeaders", [lo, slots[-1] - lo + 1])
if isinstance(r, list):
    for i, k in enumerate(r): lead[lo + i] = k
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
Lms = lambda s: (rtt.get(lead.get(s)) or 0) / 2 if rtt.get(lead.get(s)) else None
print(f"LEADERS: {len(leaders)} distinct over {len(slots)} slots; RTT answered {sum(1 for v in rtt.values() if v)}; one-way L p10/p50/p90 "
      f"{q([v/2 for v in rtt.values() if v], .1)}/{q([v/2 for v in rtt.values() if v], .5)}/{q([v/2 for v in rtt.values() if v], .9)} ms")

# 4. verdicts
wv = [(w, Lms(s)) for s, w in win if Lms(s) is not None]
data_proof = sum(1 for w, L in wv if w < L)
print(f"VERDICT, winners (n={len(wv)} with a known L): faster than a shred could reach Frankfurt (w < L): {data_proof}"
      f" -> {data_proof*100/len(wv):.0f}% of the gaps were taken before shred data could even reach us" if wv else "VERDICT: no winner with a known L")
ov = [(w, Lms(s)) for s, w in ours if Lms(s) is not None]
if ov:
    extra = [w - 2 * L - 1.1 for w, L in ov]
    print(f"VERDICT, ours (n={len(ov)}): delay after trigger p50 {q([w for w,_ in ov],.5):.1f} ms = physics 2L+1.1 p50 {q([2*L+1.1 for _,L in ov],.5):.1f} ms"
          f" + what our send path adds p10/p50/p90 {q(extra,.1):.1f}/{q(extra,.5):.1f}/{q(extra,.9):.1f} ms")
for s, w in sorted(win)[:0]: pass
json.dump({"win": win, "ours": ours, "lead": {str(k): v for k, v in lead.items() if k in set(slots)}, "rtt": rtt}, open(B + "poh-verdict.json", "w"))
