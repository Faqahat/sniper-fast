#!/usr/bin/env python3
# Backfill raw tapes for a past slot range with collect.py's parser. Same launches.jsonl / txs/*.jsonl.gz format, no
# enrichment or final pass (those would record today's state). Never reads older than the region ledger + MARGIN, so it
# cannot spend the Cube Runner long-term quota. Resumes from the last closed chunk. Stop: touch $OUT/STOP.
# Env: START_SLOT, WINDOW_END_BT (creates tracked up to this block time), END_SLOT (last slot, tail), BLOCK_RPS, OUT, TIPMAP
import os, sys, json, time, gzip, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect as c
START, END = int(os.environ["START_SLOT"]), int(os.environ["END_SLOT"]); WIN = float(os.environ["WINDOW_END_BT"])
MARGIN = int(os.environ.get("MARGIN", "20000")); OUT = c.OUT; SF = os.path.join(OUT, "state.json")
c.BEPS[:] = [os.environ.get("BLOCK_URL") or c.URL]; c._bl[:] = c._bl[:1]; c._bn[:] = [0.0]   # BLOCK_URL: another provider (URL never printed)
ch = {"f": None, "bt": 0}; cur = {"slot": START, "bt": 0}
def save(slot): json.dump(dict(slot=slot), open(SF + ".tmp", "w")); os.replace(SF + ".tmp", SF)
def close(slot):
    if ch["f"]: ch["f"].close(); ch["f"] = None; save(slot)
def chunk_write(rec):
    if ch["f"] is None:
        ch["bt"] = rec["bt"] or int(time.time())
        ch["f"] = gzip.open(os.path.join(OUT, "txs", f"txs_{ch['bt']}.jsonl.gz"), "wt", compresslevel=3)
    ch["f"].write(json.dumps(rec, separators=(",", ":")) + "\n")
c.chunk_write = chunk_write
nxt = START
if os.path.exists(SF):
    nxt = json.load(open(SF))["slot"] + 1
    for l in open(os.path.join(OUT, "launches.jsonl")):
        try: x = json.loads(l)
        except Exception: continue
        if x["slot"] < nxt: c.TRACK[x["mint"]] = x["slot"]; c.LCACHE[x["mint"]] = x; c.EARLY.setdefault(x["mint"], [])
    print("resume at", nxt, "tracked", len(c.TRACK), flush=True)
def floor():
    m = c.rpc("minimumLedgerSlot", []); return m + MARGIN if isinstance(m, int) else None
fl = floor(); tf = time.time(); last = 0; pend = collections.deque(); sub = nxt; AHEAD = 40; t0 = time.time(); n0 = 0
if fl is None: sys.exit("no ledger floor")
with ThreadPoolExecutor(8) as ex:
    while True:
        if os.path.exists(os.path.join(OUT, "STOP")): break
        if time.time() - tf > 60:
            tf = time.time(); f = floor()
            if f: fl = f
        if sub < fl:
            c.jlog("gaps.jsonl", dict(slot=sub, to=fl, why="below ledger floor, jumped")); c.ST["floor_jumps"] += 1; c.ST["floor_slots"] += fl - sub; sub = fl
        while len(pend) < AHEAD and sub <= END: pend.append((sub, ex.submit(c.get_block, sub))); sub += 1
        if not pend: break
        sl, fu = pend.popleft(); b = fu.result()
        if b is None: c.ST["blocks_failed"] += 1; c.jlog("gaps.jsonl", dict(slot=sl, why="fetch failed"))
        elif "_skip" in b: c.ST["blocks_skipped"] += 1
        else:
            bt = b.get("blockTime") or 0
            try: c.process_block(sl, b, bt <= WIN); c.ST["blocks_ok"] += 1; n0 += 1
            except Exception as e: c.ST["blocks_parse_err"] += 1; c.jlog("gaps.jsonl", dict(slot=sl, why="parse " + repr(e)[:200]))
            cur.update(slot=sl, bt=bt)
            if bt - ch["bt"] > 300: close(sl)
        while not c.EQ.empty(): c.EQ.get_nowait()   # no enrichment on a backfill
        if time.time() - last > 30:
            last = time.time(); s = dict(last_slot=cur["slot"], last_bt=cur["bt"], end=END, floor=fl, rate=round(n0 / (last - t0 + 1e-9), 2), left_h=round((END - cur["slot"]) / max(n0 / (last - t0 + 1e-9), .1) / 3600, 1), tracked=len(c.TRACK), now=last, stats=dict(c.ST))
            json.dump(s, open(os.path.join(OUT, "status.json.tmp"), "w")); os.replace(os.path.join(OUT, "status.json.tmp"), os.path.join(OUT, "status.json"))
close(cur["slot"])
print("STOPPED" if os.path.exists(os.path.join(OUT, "STOP")) else "DONE", cur, flush=True)
