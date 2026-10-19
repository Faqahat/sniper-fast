#!/usr/bin/env python3
# READ-ONLY census: rule-#2 fires from earlier zero-cost runs (paper "PAPER launch #", junk "  FIRE slot="), de-duplicated by
# mint over the union of the runs' time windows, then the two FIX2 gates applied offline:
#   near leader  = the create slot's leader is in /root/fix2/close_leaders_5ms.txt (RTT < 5 ms, measured today)
#   early create = the create's in-slot time <= X ms (on-chain truth: non-vote position x slot ms; and the engine's own
#                  erpc PoH estimate from the DETECT lines where the log has one)
# usage: census.py X log1 log2 ...
import sys, re, json, os, collections
sys.path.insert(0, "/root/indep")
from common import rpc, get_block, is_vote
X = float(sys.argv[1]); LOGS = sys.argv[2:]
SLOT_MS = 203.5
CACHE = "/root/fix2/blkcache2"; os.makedirs(CACHE, exist_ok=True)
close = {l.strip() for l in open("/root/fix2/close_leaders_5ms.txt") if l.strip()}
lr = json.load(open("/root/fix2/leader_rtt.json"))
EP0, EPL = lr["start"], lr["len"]
sp = "/root/fix2/sched_%d.json" % EP0
if os.path.exists(sp):
    sched = json.load(open(sp))
else:
    ls = rpc("getLeaderSchedule", [None])
    sched = {}
    for pk, slots in ls.items():
        for s in slots:
            sched[str(EP0 + s)] = pk
    json.dump(sched, open(sp, "w"))


def cls(c):
    return {"AgaveBam": "bam", "FireBAM": "bam", "JitoLabs": "jito", "Firedancer": "fd", "Frankendancer": "fd", "Agave": "agave"}.get(c, "harmonic" if c.startswith("Harmonic") else "other")


wins, fires, erpc_poh = [], {}, {}
for f in LOGS:
    ts = [int(m) for m in re.findall(r"t_rx=(\d+)", open(f, errors="replace").read())]
    if ts:
        wins.append((min(ts) / 1e9, max(ts) / 1e9))
    for l in open(f, errors="replace"):
        m = re.search(r"PAPER launch #\d+ slot=(\d+) mint=(\w+)", l) or re.search(r"^  FIRE slot=(\d+) mint=(\w+)", l)
        if m:
            fires.setdefault(m.group(2), int(m.group(1)))
        m = re.search(r"DETECT feed=erpc .*?slot=(\d+) .*?poh_ms=([\d.]+) .*?mint=(\w+)", l)
        if m:
            erpc_poh[m.group(3)] = float(m.group(2))
wins.sort()
merged = []
for a, b in wins:
    if merged and a <= merged[-1][1]:
        merged[-1] = (merged[-1][0], max(merged[-1][1], b))
    else:
        merged.append((a, b))
hours = sum(b - a for a, b in merged) / 3600
print(f"runs {len(LOGS)}, covered {hours:.2f} h (union of windows), unique rule-#2 fires {len(fires)} = {len(fires)/hours:.1f}/h")


def blk(s):
    p = f"{CACHE}/{s}.json"
    if os.path.exists(p):
        return json.load(open(p))
    b = get_block(s)
    if isinstance(b, dict) and "transactions" in b:
        small = {"txs": [[t["transaction"]["signatures"][0], bool(is_vote(t))] for t in b["transactions"]]}
        # mark the create of each mint: keep the account keys of creates (cheap: only txs with a Create log)
        small["creates"] = {}
        for i, t in enumerate(b["transactions"]):
            lm = (t.get("meta") or {}).get("logMessages") or []
            if any("Instruction: Create" in x for x in lm):
                small["creates"][t["transaction"]["signatures"][0]] = t["transaction"]["message"]["accountKeys"][:4]
        json.dump(small, open(p, "w"))
        return small
    return None


rows = []
for mint, slot in fires.items():
    b = blk(slot)
    truth = None
    if b and "creates" in b:
        nv = [s for s, v in b["txs"] if not v]
        csig = next((s for s, keys in b["creates"].items() if mint in keys), None)
        if csig and csig in nv:
            truth = (nv.index(csig) + 0.5) / len(nv) * SLOT_MS
    leader = sched.get(str(slot))
    info = lr["leaders"].get(leader or "", {})
    rows.append(dict(mint=mint, slot=slot, leader=leader, close=leader in close, rtt=info.get("rtt"), cls=cls(info.get("client", "")),
                     truth=truth, poh=erpc_poh.get(mint)))
json.dump(rows, open("/root/fix2/census_rows.json", "w"))
n = len(rows)
near = [r for r in rows if r["close"]]
early = [r for r in rows if r["truth"] is not None and r["truth"] <= X]
both = [r for r in near if r["truth"] is not None and r["truth"] <= X]
unk = sum(1 for r in rows if r["truth"] is None)
print(f"near leader (<5 ms): {len(near)}/{n} ({len(near)/n:.0%}) = {len(near)/hours:.1f}/h")
print(f"create <= {X:.0f} ms (chain): {len(early)}/{n} ({len(early)/n:.0%}); unknown position {unk}")
print(f"BOTH gates: {len(both)}/{n} ({len(both)/n:.0%}) = {len(both)/hours:.1f}/h  (rule #2 survivors per hour)")
pe = [r for r in near if r["poh"] is not None]
if pe:
    print(f"  engine erpc-PoH estimate available for {len(pe)}/{len(near)} near fires; both-gates by engine estimate {sum(1 for r in pe if r['poh'] <= X)}/{len(pe)}")
by = collections.Counter(r["cls"] for r in rows); byn = collections.Counter(r["cls"] for r in near); byb = collections.Counter(r["cls"] for r in both)
print("by leader client (all / near / both): " + ", ".join(f"{k} {by[k]}/{byn[k]}/{byb[k]}" for k in sorted(by, key=lambda k: -by[k])))
for XX in (130, 150, 170, 200):
    bb = sum(1 for r in near if r["truth"] is not None and r["truth"] <= XX)
    print(f"  X={XX}: both gates {bb}/{n} = {bb/hours:.1f}/h")
