#!/usr/bin/env python3
# READ-ONLY, zero cost: how long after OUR detection of a create does an RPC node's PROCESSED state contain the new mint?
# (proxy for the Jito block engine's simulation state: a bundle simulated before its bank has the create fails as
# "would-fail"). Tails the engine log; for each first-arrival create that passed the base filter, polls
# getAccountInfo(mint, processed) every 20 ms on constant-k RPC until it exists (max 3 s). usage: statelag.py <log> <minutes>
import sys, re, json, os, time, threading, urllib.request, collections
LOG, MIN = sys.argv[1], float(sys.argv[2])
TOK = os.environ["CONSTANTK_TOKEN"]; RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
sched = json.load(open("/root/fix2/sched_458784000.json"))
lr = json.load(open("/root/fix2/leader_rtt.json"))["leaders"]
out = open("/root/fix2/statelag.jsonl", "a")
lock = threading.Lock()


def call(m, p):
    r = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=5))


def watch(slot, t_rx, mint):
    t_start = time.time_ns()
    first, n = None, 0
    while (time.time_ns() - t_rx) < 3e9:
        n += 1
        try:
            v = call("getAccountInfo", [mint, {"encoding": "base64", "commitment": "processed", "dataSlice": {"offset": 0, "length": 0}}])
            if v.get("result", {}).get("value") is not None:
                first = (time.time_ns() - t_rx) / 1e6
                break
        except Exception:
            pass
        time.sleep(0.02)
    ld = sched.get(str(slot)); info = lr.get(ld or "", {})
    rec = {"slot": slot, "mint": mint, "start_ms": (t_start - t_rx) / 1e6, "visible_ms": first, "polls": n, "rtt": info.get("rtt"), "client": info.get("client")}
    with lock:
        out.write(json.dumps(rec) + "\n"); out.flush()


f = open(LOG, errors="replace"); f.seek(0, 2)
end = time.time() + MIN * 60
while time.time() < end:
    l = f.readline()
    if not l:
        time.sleep(0.005); continue
    m = re.search(r"DETECT feed=\S+ first=1 .*?slot=(\d+) t_rx=(\d+) .*?mint=(\w+) .*verdict=pass", l)
    if m:
        threading.Thread(target=watch, args=(int(m.group(1)), int(m.group(2)), m.group(3)), daemon=True).start()
time.sleep(4)
rows = [json.loads(x) for x in open("/root/fix2/statelag.jsonl")]
def q(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(round(p * (len(v) - 1))))] if v else float("nan")
for name, sel in (("all", lambda r: True), ("near <5ms", lambda r: r["rtt"] is not None and r["rtt"] < 5), ("far >=5ms", lambda r: r["rtt"] is None or r["rtt"] >= 5)):
    v = [r["visible_ms"] for r in rows if sel(r) and r["visible_ms"] is not None]
    miss = sum(1 for r in rows if sel(r) and r["visible_ms"] is None)
    print(f"{name}: n={len(v)} (+{miss} not visible in 3 s): mint visible at processed after our detection p10 {q(v,.1):.0f} p50 {q(v,.5):.0f} p90 {q(v,.9):.0f} ms; first poll at p50 {q([r['start_ms'] for r in rows if sel(r)],.5):.1f} ms")
