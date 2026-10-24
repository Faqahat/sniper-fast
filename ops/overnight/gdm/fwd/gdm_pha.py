#!/usr/bin/env python3
# GDM forward test, step 1: INCREMENTAL phase-A extraction (same code as ops/select/a_extract.py, exec'd) of the R2 raw
# collection into OUR OWN dir (default /home/moiz/sniper-data/collect/phaseA_gdmfwd). Only raw chunks that start at/after
# START_TS; a chunk is (re-)extracted when it is new or its size changed since the last run (the newest chunk grows while
# the dry-run loop syncs it). Output files are staged and renamed, so readers never see half-written bucket files.
# Named gdm_pha (not a_extract) so the dry-run loop's "a_extract running?" checks are not triggered by us.
# usage: python3 -I gdm_pha.py <run dir> <out dir> <start_ts> [procs=6]
import sys, os, json, glob, shutil, gzip
from multiprocessing import Pool
RUN, OUT, START = sys.argv[1], sys.argv[2], float(sys.argv[3]); PROCS = int(sys.argv[4]) if len(sys.argv) > 4 else 6
STAGE = OUT + ".stage"
src = open("/home/moiz/sniper/ops/select/a_extract.py").read()
sys.argv = ["a_extract.py", RUN, STAGE, str(PROCS)]
g = {"__name__": "a_extract_lib"}; exec(src[:src.index('if __name__ == "__main__":')], g)
def job(path):
    n = g["work"](path)
    return path, n
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True); shutil.rmtree(STAGE, ignore_errors=True)
    for b in range(256): os.makedirs(os.path.join(STAGE, f"b{b:03d}"), exist_ok=True); os.makedirs(os.path.join(OUT, f"b{b:03d}"), exist_ok=True)
    donef = os.path.join(OUT, "_done.json"); done = json.load(open(donef)) if os.path.exists(donef) else {}
    files = sorted(f for f in glob.glob(os.path.join(RUN, "txs", "txs_*.jsonl.gz")) if float(os.path.basename(f)[4:].split(".")[0]) >= START)
    todo = [f for f in files if done.get(os.path.basename(f)) != os.path.getsize(f)]
    sizes = {f: os.path.getsize(f) for f in todo}                      # size BEFORE extraction (a later sync re-triggers)
    tot = 0
    with Pool(PROCS) as p:
        for path, n in p.imap_unordered(job, todo): tot += n
    for b in range(256):                                                 # move staged bucket files into place (atomic renames)
        sd = os.path.join(STAGE, f"b{b:03d}")
        for fn in os.listdir(sd): os.replace(os.path.join(sd, fn), os.path.join(OUT, f"b{b:03d}", fn))
    shutil.rmtree(STAGE, ignore_errors=True)
    for f in todo: done[os.path.basename(f)] = sizes[f]
    json.dump(done, open(donef + ".tmp", "w")); os.replace(donef + ".tmp", donef)
    # data end = last block time in the newest raw chunk (tolerates a chunk that is still being synced)
    mx = 0
    if files:
        try:
            for line in gzip.open(files[-1], "rt"):
                try: bt = json.loads(line).get("bt") or 0
                except Exception: continue
                mx = max(mx, bt)
        except (EOFError, OSError, Exception): pass
    json.dump(dict(data_end=mx, newest=os.path.basename(files[-1]) if files else None), open(os.path.join(OUT, "_data_end.json"), "w"))
    print(f"phase A: {len(files)} chunks since start, extracted {len(todo)} now ({tot} txs); newest chunk ends at bt {mx}", flush=True)
