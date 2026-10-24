#!/usr/bin/env python3
# HOW COULD WE HAVE WON THE REVERTED BUYS? (read-only) For each reverted PROD dip buy: the exact trade that pushed the curve past our
# guard (first trade after the dump after which our spend would get fewer tokens than our min_out), who sent it, how (fees / tip
# service), where it landed vs the dump and vs us, and when OUR engine saw it vs when we fired / saw our own tx -> what it took to win.
import os, sys, json, time, urllib.request, collections, statistics, concurrent.futures as cf
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/hkq7")
import rp
from ahead_fees import fees, rpc            # same read-only helpers (priority fee / tip / landing service of a tx)
D = "/home/moiz/sniper/ops/overnight/hkq7"
R = [r for r in json.load(open(f"{D}/replay_reverted.json")) if r["result"] == "buy_failed"]
T = json.load(open(f"{D}/2g_timing.json")); TAPE = json.load(open(f"{D}/2g_tape.json"))
seen = {x["sig"]: x["t"] for x in TAPE if x.get("sig") and x.get("t")}
NAMES = {"HkQ7hMjy": "HkQ7", "haqqiUUX": "haqqiUUX", "DYXDDrZC": "DYXDDrZC"}
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
BLK = {}
def where(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t: return None
    if t["slot"] not in BLK:
        b = rpc("getBlock", [t["slot"], {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 0, "rewards": False}]); BLK[t["slot"]] = b["signatures"] if b else []
    s = BLK[t["slot"]]; return (t["slot"], s.index(sig) if sig in s else None)
F = {}
# min_out of each fire (guard): from the server fire records (2g_timing has only paths) -> re-pull
import subprocess
raw = subprocess.run(["ssh", "-p", "1996", "-o", "ConnectTimeout=15", "it@84.32.100.36", "sudo python3 -I -c \"import json\nfor i in range(1,8):\n  for l in open(f'/root/prod/runs/dip_r{i}.jsonl'):\n    if '\\\"ev\\\":\\\"fire\\\"' in l:\n      r=json.loads(l); print(json.dumps(dict(sig=r['buy_sig'], min_out=r['min_out'], spend=r['spend'], t_fire=r['t_fire'], t_dump_rx=r['t_dump_rx'], dump_sig=r['dump_sig'])))\""],
                     capture_output=True, text=True).stdout
for l in raw.splitlines():
    try: x = json.loads(l); F[x["sig"]] = x
    except Exception: pass
with cf.ThreadPoolExecutor(8) as ex: DW = list(ex.map(lambda r: where(F[r["sig"]]["dump_sig"]) if r["sig"] in F else None, R))
L = rp.load_launches(); byb = collections.defaultdict(set)
for r in R:
    if r["mint"] in L: byb[(L[r["mint"]]["run"], rp.bucket(r["mint"]))].add(r["mint"])
tapes = {}
for k, ms in byb.items(): tapes.update(rp.read_bucket(k[0], k[1], ms))
rows = []
for r, dw in zip(R, DW):
    f = F.get(r["sig"]); tr = tapes.get(r["mint"], [])
    if not f or not dw or dw[1] is None or r.get("idx") is None: continue
    me = (r["slot"], r["idx"]); dpos = (dw[0], dw[1])
    btw = [t for t in tr if dpos < (t["s"], t["i"]) < me]
    cross = None
    for t in btw:
        fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4; X = int(f["spend"] / (1 + fr)); q = t["vtok"] * X // (t["vsol"] + X)
        if q < f["min_out"]: cross = t; break
    if cross is None: rows.append(dict(sig=r["sig"], cat="no single crossing found (guard tripped by our own size / fees)")); continue
    tm = T.get(r["sig"]) or {}
    t_seen_cross = seen.get(cross["sig"]); t_fire = f["t_fire"]; t_seen_me = tm.get("buy_first_rx")
    before_fire = t_seen_cross is not None and t_seen_cross < t_fire
    same_slot_as_dump = cross["s"] == dw[0]
    cat = ("price had ALREADY moved before we fired" if before_fire else
           ("lost the race inside the SAME slot" if cross["s"] == r["slot"] else "we landed a slot LATER than the crossing buy"))
    rows.append(dict(sig=r["sig"], run=r["run"], cat=cat, cross_sig=cross["sig"], cross_user=cross["user"], who=NAMES.get(cross["user"][:8], "profitable bot" if cross["user"] in COH else "other"),
                     cross_sol=cross["sol"] / 1e9, cross_after_dump_pos=(cross["s"] - dw[0], cross["i"] - dw[1]), cross_same_slot_as_dump=same_slot_as_dump,
                     we_after_cross_pos=(r["slot"] - cross["s"], r["idx"] - cross["i"]), n_between=len(btw),
                     ms_seen_cross_minus_fire=(t_seen_cross - t_fire) / 1e6 if t_seen_cross else None,
                     ms_seen_me_minus_cross=(t_seen_me - t_seen_cross) / 1e6 if (t_seen_me and t_seen_cross) else None,
                     ms_fire_minus_dump_rx=(t_fire - f["t_dump_rx"]) / 1e6, client=r.get("client"), route=r.get("route")))
sigs = sorted({x["cross_sig"] for x in rows if x.get("cross_sig")})
with cf.ThreadPoolExecutor(10) as ex: FE = dict(zip(sigs, ex.map(fees, sigs)))
for x in rows:
    if x.get("cross_sig") and FE.get(x["cross_sig"]): x.update(cross_prio=FE[x["cross_sig"]]["prio"], cross_tip=FE[x["cross_sig"]]["tip"], cross_svc=FE[x["cross_sig"]]["svc"])
json.dump(rows, open(f"{D}/howtowin.json", "w"), default=str)
med = lambda v: statistics.median(v) if v else float("nan")
print(f"reverted buys analysed: {len(rows)}")
for c, n in collections.Counter(x["cat"] for x in rows).most_common():
    v = [x for x in rows if x["cat"] == c]
    print(f"\n=== {c}: {n}")
    if not v[0].get("cross_sig"): continue
    print(f"   crossing buy: same slot as the dump {sum(x['cross_same_slot_as_dump'] for x in v)}/{n} | median {med([x['cross_after_dump_pos'][1] for x in v if x['cross_after_dump_pos'][0] == 0])} positions after the dump (same-slot ones) | "
          f"median size {med([x['cross_sol'] for x in v]):.2f} SOL")
    print(f"   who: {collections.Counter(x['who'] for x in v).most_common()}")
    print(f"   how it was sent: {collections.Counter(x.get('cross_svc', '?') for x in v).most_common(5)} | priority med {med([x['cross_prio'] for x in v if 'cross_prio' in x]):.5f} tip med {med([x['cross_tip'] for x in v if 'cross_tip' in x]):.4f}")
    a = [x["ms_seen_cross_minus_fire"] for x in v if x["ms_seen_cross_minus_fire"] is not None]; b = [x["ms_seen_me_minus_cross"] for x in v if x["ms_seen_me_minus_cross"] is not None]
    print(f"   our engine saw the crossing buy {med(a):+.1f} ms after our fire (n {len(a)}); saw OUR tx {med(b):+.1f} ms after the crossing buy (n {len(b)}) | our reaction (dump seen -> fire) {med([x['ms_fire_minus_dump_rx'] for x in v]):.1f} ms")
    print(f"   positions we landed behind it (same slot): {med([x['we_after_cross_pos'][1] for x in v if x['we_after_cross_pos'][0] == 0])} | leader client {collections.Counter(x['client'] for x in v).most_common(3)}")
