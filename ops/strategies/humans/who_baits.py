#!/usr/bin/env python3
# Bot or human? (owner 10-24 ~21:00 PKT: "check current bots, I think the ones above aren't bots"). For the top quiet-token
# baiters (F7 family, 46 h) and the most active baiters of the last ~7 h, read every tx they sent in the recordings (R3 + the
# new day so far): trades per hour, longest idle gap, hours active (PKT), reaction time after the token's previous trade,
# priority fee, tip relays, extra programs and recurring fee receivers (trading terminals leave these). READ-ONLY, local data.
import json, gzip, os, sys, collections, statistics, datetime
from multiprocessing import Pool
DIRS = ["/home/moiz/sniper-data/collect/run_20261023_1426/txs", "/home/moiz/sniper-data/collect/run_20261024_1425/txs"]
TIP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
COMMON = {"11111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "ComputeBudget111111111111111111111111111111",
          "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
          "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"}
FULL = sys.argv[1].split(",") if len(sys.argv) > 1 else []
PREF = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else []
files = sorted(f"{d}/{f}" for d in DIRS if os.path.isdir(d) for f in os.listdir(d))
def work(fn):
    out = []
    try:
        for l in gzip.open(fn, "rt"):
            hit = [w for w in FULL if w in l] + [p for p in PREF if p in l]
            if not hit: continue
            r = json.loads(l); sg = (r.get("signers") or [""])[0]
            if any(sg == w for w in FULL) or any(sg.startswith(p) for p in PREF): out.append(r)
    except (EOFError, OSError): pass
    return out
if __name__ == "__main__":
    by = collections.defaultdict(list)
    with Pool(8) as p:
        for part in p.imap_unordered(work, files, chunksize=4):
            for r in part: by[r["signers"][0]].append(r)
    res = {}
    for w, txs in by.items():
        txs.sort(key=lambda r: (int(r["s"]), int(r["i"])))
        bts = [int(r["bt"]) for r in txs]
        hours = collections.Counter((datetime.datetime.fromtimestamp(b, datetime.UTC) + datetime.timedelta(hours=5)).hour for b in bts)
        gaps = sorted((b - a for a, b in zip(bts, bts[1:])), reverse=True)
        span_h = (bts[-1] - bts[0]) / 3600 if len(bts) > 1 else 0
        progs = collections.Counter(p for r in txs for p in set(r.get("progs") or []) if p not in COMMON)
        rel = collections.Counter("+".join(sorted({TIP.get(a, "?") for a, _ in (r.get("tips") or [])})) or "no tip" for r in txs)
        recv = collections.Counter()
        for r in txs:
            for a, d in (r.get("sd") or []):
                if a != w and int(d) > 0 and a not in TIP and int(d) < 50_000_000: recv[a] += 1
        cup = [int(r.get("cup") or 0) for r in txs]
        ok = sum(1 for r in txs if not r.get("err") or r.get("err") == "None")
        buys = sum(1 for r in txs if "Buy" in " ".join(r.get("ixn") or []))
        res[w] = dict(n=len(txs), ok=ok, buys=buys, span_h=round(span_h, 1), per_h=round(len(txs) / max(span_h, 0.1), 1),
                      first=(datetime.datetime.fromtimestamp(bts[0], datetime.UTC) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M"),
                      last=(datetime.datetime.fromtimestamp(bts[-1], datetime.UTC) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M"),
                      gaps_h=[round(g / 3600, 1) for g in gaps[:3]], hours=dict(sorted(hours.items())),
                      prio_med=statistics.median(cup) if cup else 0, relays=dict(rel.most_common(4)), progs=dict(progs.most_common(5)),
                      recv=dict(recv.most_common(4)), cu_lim=statistics.median([int(r.get("cul") or 0) for r in txs]))
    json.dump(res, open("/home/moiz/sniper-data/strategies/who_baits.json", "w"), indent=1)
    for w, v in sorted(res.items(), key=lambda kv: -kv[1]["n"]):
        print(f"\n{w}\n  txs {v['n']} (ok {v['ok']}, buys {v['buys']}) over {v['span_h']} h = {v['per_h']}/h; first {v['first']} last {v['last']}; longest idle gaps {v['gaps_h']} h")
        print(f"  hours active (PKT): {v['hours']}")
        print(f"  priority median {v['prio_med']} uL/CU, CU limit median {v['cu_lim']}; relays {v['relays']}")
        print(f"  extra programs {v['progs']}")
        print(f"  recurring small SOL receivers {v['recv']}")
