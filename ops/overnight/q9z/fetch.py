#!/usr/bin/env python3
# READ-ONLY, RESUMABLE: raw jsonParsed transactions of 9qz7cW that our collector does NOT already have (sd rows), cached
# gzipped in txc/<sig>.json.gz, owner's RPC only (paced 3.8 req/s; public mainnet-beta answered 429). Budgeted:
#   phase 1: every successful tx from FULL_FROM (36 h window) to now, newest first;
#   phase 1b: collector-covered txs of NON-SOL-quoted tokens (the sd rows lack their quote-token leg);
#   phase 2: a spread random sample of failed txs not in the collector (fee + error code);
#   phase 3: older successful txs (back to the RPC's history start) only in EVEN UTC hours (complete hour blocks, so
#            round trips stay whole; odd hours are not fetched -> the older period is a ~50% sample, scaled in the report).
# usage: python3 -I fetch.py [n_failed_sample=400]
import sys, os, json, gzip, time, threading, collections, random, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from rpcq import rpc
C = os.path.join(HERE, "txc"); os.makedirs(C, exist_ok=True)
NF = int(sys.argv[1]) if len(sys.argv) > 1 else 400
FULL_FROM = 1792594800          # 2026-10-21 15:00 UTC
S = json.load(open(os.path.join(HERE, "sigs.json")))
sd = set()
for f in ("sd_R1_q9z.jsonl", "sd_R2_q9z.jsonl"):
    for l in open(os.path.join(HERE, f)): sd.add(json.loads(l)[1])
sd |= set(json.load(open(os.path.join(HERE, "raw_sigs.json"))))          # raw collector txs (R2 continues past the sd extraction)
have = lambda s: os.path.exists(os.path.join(C, s + ".json.gz"))
ok = [s for s in S if s.get("err") is None and s["signature"] not in sd]      # newest first
hr = lambda s: datetime.datetime.fromtimestamp(s.get("blockTime") or 0, datetime.timezone.utc).hour
p1 = [s["signature"] for s in ok if (s.get("blockTime") or 0) >= FULL_FROM]
p3 = [s["signature"] for s in ok if (s.get("blockTime") or 0) < FULL_FROM and hr(s) % 2 == 0]
bad = [s["signature"] for s in S if s.get("err") is not None and s["signature"] not in sd]
random.seed(7); p2 = [bad[i] for i in sorted(random.sample(range(len(bad)), min(NF, len(bad))))]
json.dump(dict(full_from=FULL_FROM, p1=len(p1), p3_even_hours=len(p3),
               p3_odd_hours_skipped=sum(1 for s in ok if (s.get("blockTime") or 0) < FULL_FROM and hr(s) % 2 == 1), failed_sample=p2),
          open(os.path.join(HERE, "fetch_plan.json"), "w"))
lock = threading.Lock(); cnt = collections.Counter()
P = dict(encoding="jsonParsed", maxSupportedTransactionVersion=1)
def run(lst, tag):
    todo = collections.deque([s for s in lst if not have(s)])
    print(time.strftime("%H:%M:%S"), tag, "to fetch", len(todo), "of", len(lst), flush=True)
    def worker():
        while True:
            with lock:
                if not todo: return
                sig = todo.popleft()
            r = rpc("getTransaction", [sig, P])
            if r:
                with gzip.open(os.path.join(C, sig + ".json.gz"), "wt") as f: json.dump(r, f)
            with lock:
                cnt[tag] += 1; cnt[tag + "_miss"] += 0 if r else 1
                if cnt[tag] % 500 == 0: print(time.strftime("%H:%M:%S"), dict(cnt), "left", len(todo), flush=True)
    th = [threading.Thread(target=worker) for _ in range(5)]
    for t in th: t.start()
    for t in th: t.join()
    print(time.strftime("%H:%M:%S"), tag, "done", dict(cnt), flush=True)
# 03:13 UTC: the shared RPC started answering 429 (all agents together), ~1.5 tx/s effective. Budget cut:
#  - p1b dropped: non-SOL quote legs are decoded from the pump.fun V3 trade events in the collector's raw txs instead;
#  - p2 dropped: failed-tx fees come from the collector (19.7k measured) + SOL-balance continuity in fetched windows;
#  - p3 cut to hourly SOL-balance checkpoints (first + last successful tx of every older hour) + 2 full hour blocks.
olds = sorted([s for s in ok if (s.get("blockTime") or 0) < FULL_FROM], key=lambda s: s["slot"])
byh = collections.defaultdict(list)
for s in olds: byh[datetime.datetime.fromtimestamp(s["blockTime"], datetime.timezone.utc).strftime("%m-%d %H")].append(s["signature"])
chk = [v[0] for v in byh.values()] + [v[-1] for v in byh.values()]
blocks = [sg for h in ("10-20 18", "10-21 06") for sg in byh.get(h, [])]
json.dump(dict(checkpoints=chk, blocks=["10-20 18", "10-21 06"]), open(os.path.join(HERE, "fetch_plan_cut.json"), "w"))
run(p1, "p1"); run(chk, "p3chk"); run(blocks, "p3blk")
