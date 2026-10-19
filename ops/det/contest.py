#!/usr/bin/env python3
# READ-ONLY: contested rate of FIRED paper launches, checked on chain. For each (slot, mint) of a "PAPER launch" line in
# the given logs: block S (create + every later tx on the mint in S, glued creator bundle) and S+1 (every OK tx on the
# mint), then race_lib labels: outsiders in S (outS_n), in S+1 (outS1_n), in S or S+1 (out01_n). Cached, resumable.
# usage: contest.py <out.jsonl> <workers> <log> [<log> ...]
import sys, re, json, os, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/det")
from rl import block_record, s1_record

OUT, NW, LOGS = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
pairs = {}
for lg in LOGS:
    for l in open(lg, errors="replace"):
        m = re.search(r"PAPER launch #\d+ slot=(\d+) mint=(\w+)", l)
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
        if b.get("missing") == "create_not_in_block":
            for S2 in (S - 1, S + 1, S - 2, S + 2):
                b2 = block_record(S2, m)
                if "missing" not in b2:
                    b, S = b2, S2
                    break
        s = s1_record(m, b["csig"], S, win=1, fetch_to=1, cap=120) if "csig" in b else None
        rec = {"mint": m, "slot": S, "feed_slot": sm[0], "b": b, "s": s}
    except Exception as ex:
        rec = {"mint": m, "slot": S, "exc": repr(ex)[:200]}
    with lk:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


with ThreadPoolExecutor(NW) as ex:
    list(ex.map(work, todo))
print("FINISHED", len(todo), flush=True)
