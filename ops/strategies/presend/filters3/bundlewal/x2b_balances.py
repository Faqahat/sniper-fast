#!/usr/bin/env python3
"""BUNDLEWAL step 2b [MEASURED]: token-balance rows (tb) of every successful tx on the traded mints (incl. plain SPL
transfers, which carry no TradeEvent). Row: (s, i, has_trade_event, signer, [(owner, pre, post), ...]).
Out: bal_<rec>.pkl {mint: [rows]}.   (Original step 2 doc follows.)
BUNDLEWAL step 2 [MEASURED]: full on-curve trade history of every traded mint from the raw launch recordings.
Per recording: mints = positions whose fill time lies inside it. Every decoded pump.fun TradeEvent on those mints ->
row (s, i, buy, sol, tok, user, vtok_post) where vtok_post = mint's largest post balance in tb + 73e12 (replay4 rule).
Also the create record (slot, idx, creator) from launches.jsonl.
Out: /home/it/sniper-data/filters3/bundlewal/trades_<rec>.pkl {"trades": {mint: [rows]}, "create": {mint: (s, i, creator)}}
usage: x2_extract.py 1028 1029 ..."""
import sys, os, gzip, json, glob, pickle, collections
from multiprocessing import Pool
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/replay4")
from ev import decode
OUT = "/home/it/sniper-data/filters3/bundlewal"
C = "/data/tapes/collect"
RECS = {"1028": "run_20261028_1405", "1029": "run_20261029_1400", "1030": "run_20261030_1355",
        "1031": "run_20261031_1350", "1102": "run_20261102_1250", "1103": "run_20261103_1245"}
VOFF = 73_000_000_000_000
WANT = None

def init(w):
    global WANT; WANT = w

def job(fn):
    out = collections.defaultdict(list)
    try:
        with gzip.open(fn, "rt", errors="replace") as f:
            for l in f:
                i = l.find('"mints":[')
                if i < 0: continue
                seg = l[i + 9:l.find("]", i)]
                if not any(x.strip('" ') in WANT for x in seg.split(",") if x): continue
                try: d = json.loads(l)
                except Exception: continue
                if d.get("err") is not None: continue
                tm = set()
                for e in d.get("ev") or []:
                    t = decode(e)
                    if t: tm.add(t["mint"])
                rows = collections.defaultdict(list)
                for row in d.get("tb") or []:
                    if len(row) >= 4 and row[0] in WANT:
                        rows[row[0]].append((row[1], row[2] or 0, row[3] or 0))
                sg = (d.get("signers") or [None])[0]
                for m, rr in rows.items():
                    out[m].append((d["s"], d.get("i") or 0, m in tm, sg, rr))
    except (EOFError, OSError) as ex:
        print("  truncated", fn, ex, flush=True)
    return dict(out)

if __name__ == "__main__":
    pos = [json.loads(l) for l in open(f"{OUT}/positions.jsonl")]
    for rec in sys.argv[1:]:
        rd = f"{C}/{RECS[rec]}"
        rj = json.load(open(f"{rd}/run.json"))
        files = sorted(glob.glob(f"{rd}/txs/*.jsonl.gz"))
        last = int(os.path.basename(files[-1]).split("_")[1].split(".")[0]) + 300
        want = {p["mint"] for p in pos if rj["start_time"] + 600 <= p["fill_t"] <= last}
        create = {}
        print(rec, "mints", len(want), "creates found", len(create), "files", len(files), flush=True)
        trades = collections.defaultdict(list)
        with Pool(7, initializer=init, initargs=(want,)) as p:
            for k, r in enumerate(p.imap_unordered(job, files, chunksize=2)):
                for m, v in r.items(): trades[m].extend(v)
                if k % 40 == 0: print(f"  {rec} {k}/{len(files)}", flush=True)
        for m in trades: trades[m].sort(key=lambda x: (x[0], x[1]))
        pickle.dump(dict(trades), open(f"{OUT}/bal_{rec}.pkl", "wb"))
        print(rec, "done mints with trades", len(trades), "rows", sum(len(v) for v in trades.values()), flush=True)
