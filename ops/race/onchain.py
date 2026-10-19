#!/usr/bin/env python3
# READ-ONLY. For (slot, mint) pairs found in engine logs (FIRE / PAPER launch / RACE lines) fetch block S
# (create + every later tx on the mint) and S+1..S+8 (race_lib), cache to <out.jsonl>. Resumable.
# usage: onchain.py <out.jsonl> <workers> <log> [<log> ...]   (env ONLY=fire|race_pass|race_all to restrict)
import sys, re, json, os, threading, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/race")
from race_lib import block_record, s1_record

OUT, NW, LOGS = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
pairs = {}
for lg in LOGS:
    for l in open(lg, errors="replace"):
        m = re.search(r"(?:FIRE|PAPER launch #\d+|RACE \w+) slot=(\d+) mint=(\w+)", l)
        if m:
            pairs.setdefault(m.group(2), int(m.group(1)))
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            done.add(json.loads(l)["mint"])
        except Exception:
            pass
todo = [(s, m) for m, s in pairs.items() if m not in done]
print("pairs", len(pairs), "todo", len(todo), flush=True)
lk = threading.Lock()
fh = open(OUT, "a")


def work(sm):
    S, m = sm
    try:
        b = block_record(S, m)
        if "missing" in b and b["missing"] == "create_not_in_block":
            # the feed slot can be off by one (shred slot vs produced block): try neighbours
            for S2 in (S - 1, S + 1):
                b2 = block_record(S2, m)
                if "missing" not in b2:
                    b, S = b2, S2
                    break
        s = s1_record(m, b["csig"], S) if "csig" in b else None
        rec = {"mint": m, "slot": S, "b": b, "s": s}
    except Exception as ex:
        rec = {"mint": m, "slot": S, "exc": repr(ex)[:200]}
    with lk:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


with ThreadPoolExecutor(NW) as ex:
    list(ex.map(work, todo))
print("FINISHED", len(todo), time.strftime("%H:%M:%S"), flush=True)
