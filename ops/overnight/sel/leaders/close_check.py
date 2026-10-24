#!/usr/bin/env python3
# Only trade when the leader of the slot our buy would land in is CLOSE to our server (≤5 ms / ≤12 ms RTT lists from the
# server's /root/fix2)? Live paper trades (since 19:32 PKT) and the 12.3 h backtest picks (TEST), 35 / 75 ms, main exit.
# Leader of the landing slot at 35 ms from getLeaderSchedule (read-only RPC).
import os, sys, json, collections, urllib.request
os.environ.update(RP_PHASEA_R2="phaseA_sel", RP_PHASEA_R3="phaseA_r3", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_B="0.5")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
import live_exits as LE
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    return json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))["result"]
C5 = set(l.strip() for l in open("leaders/close_leaders_5ms.txt") if l.strip()); C12 = set(l.strip() for l in open("leaders/close_leaders_12ms.txt") if l.strip())
SCHED = {}
def leader(slot):
    ep = (slot - 459216000) // 432000 * 432000 + 459216000
    if ep not in SCHED:
        s = rpc("getLeaderSchedule", [slot]) or {}; SCHED[ep] = {ep + i: ident for ident, idxs in s.items() for i in idxs}
    return SCHED[ep].get(slot)
def picks_live():
    for r in map(json.loads, open("live_trades.jsonl")): yield r["m"], r["age"]
def picks_test():
    for l in open("picks_imit1_top4_test.jsonl"): r = json.loads(l); yield r["m"], r["age"]
for name, src in (("LIVE since 19:32 PKT", picks_live), ("BACKTEST 12.3 h (TEST)", picks_test)):
    agg = collections.defaultdict(lambda: {"35": [0.0, 0, 0, 0], "75": [0.0, 0, 0, 0]})
    for m, age in src():
        tr = X.rp.read_bucket(X.L[m]["run"], X.rp.bucket(m), {m}).get(m, []); S0 = X.L[m]["slot"]
        k = next((j for j, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= X.MIN_SELL and not t.get("syn") and round((t["s"] - S0) * X.SMS / 1000, 2) == age), None)
        if k is None: continue
        s_land = int((X.arr(tr[k]) + 35) // X.SMS); ld = leader(s_land)
        grp = "close ≤5 ms" if ld in C5 else ("near ≤12 ms" if ld in C12 else "far")
        for L in ("35", "75"):
            x = LE.detail(X, tr, k, int(L)); a = agg[grp][L]; a[3] += 1
            if x is None: continue
            if not x["f"]: a[0] -= 0.0002; continue
            p = x[LE.MAIN][0]; a[0] += p; a[1] += 1; a[2] += p > 0
    print(f"== {name}")
    for g in ("close ≤5 ms", "near ≤12 ms", "far"):
        a = agg[g]
        if a["35"][3]: print(f"  {g:12s} picks {a['35'][3]:4d} | 35 ms {a['35'][0]:+6.2f} SOL ({a['35'][2]}/{a['35'][1]} won) | 75 ms {a['75'][0]:+6.2f} ({a['75'][2]}/{a['75'][1]})")
