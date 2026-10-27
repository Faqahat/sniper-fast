#!/usr/bin/env python3
"""HAQQ_SEL step 2 (read-only, offline): the regular-dip (M2) study rows for the 24 h window, built with the study's own code,
unchanged (ops/select/a_extract.py -> patterns/p1_build.py -> dipdetect/dd1_build.py; the same three stages dd20_shadow_eval.py
runs), at 0.50 SOL (DD_SIZE), into /home/moiz/sniper-data/haqq_sel/m2/work. Only paths are redirected:
  * the recording = a merged folder (symlinks) of run_20261026_1415 + run_20261027_1410 chunks covering the window -16/+11 min,
    and both runs' launches.jsonl concatenated;
  * the slot leaders (near-leader flags FRA / AMS) from the epoch 1068 / 1069 schedules (h0_schedule.py), since the study's
    leader map ends at epoch 1066.
Nothing here sends anything or touches an engine, server or config."""
import os, sys, glob, json, time, pickle, shutil
os.environ["DD_SIZE"] = "0.5"
import numpy as np
from multiprocessing import Pool
DIPD = "/home/moiz/sniper/ops/strategies/dipdetect"; PATTERNS = "/home/moiz/sniper/ops/strategies/patterns"; SELECT = "/home/moiz/sniper/ops/select"
sys.path.insert(0, DIPD)
DATA = "/home/moiz/sniper-data/haqq_sel"; M2 = f"{DATA}/m2"; RUN = f"{M2}/run_HQ"; WORK = f"{M2}/work"; TAG = "HQ"
W0 = 1793038500; W1 = 1793124900
PROCS = 10


def setup_run():
    os.makedirs(f"{RUN}/txs", exist_ok=True); n = 0
    for r in ("run_20261026_1415", "run_20261027_1410"):
        for f in sorted(glob.glob(f"/home/moiz/sniper-data/collect/{r}/txs/txs_*.jsonl.gz")):
            ts = int(os.path.basename(f).split("_")[1].split(".")[0])
            if W0 - 16 * 60 <= ts <= W1 + 11 * 60:
                dst = f"{RUN}/txs/{os.path.basename(f)}"
                if not os.path.exists(dst): os.symlink(f, dst)
                n += 1
    if not os.path.exists(f"{RUN}/launches.jsonl"):
        with open(f"{RUN}/launches.jsonl", "w") as o:
            for r in ("run_20261026_1415", "run_20261027_1410"):
                for l in open(f"/home/moiz/sniper-data/collect/{r}/launches.jsonl"): o.write(l if l.endswith("\n") else l + "\n")
    return sorted(glob.glob(f"{RUN}/txs/*.jsonl.gz"))


def leader_map():
    LS0 = 1068 * 432000
    scs = [json.load(open(f"{DATA}/schedule_{e}.json")) for e in (1068, 1069)]
    ids = sorted(set().union(*[set(s["ids"]) for s in scs])); ix = {u: i for i, u in enumerate(ids)}
    lead = np.full(2 * 432000, -1, np.int32)
    for s in scs:
        lead[s["start"] - LS0:s["start"] - LS0 + len(s["slot_leader"])] = [ix[s["ids"][i]] for i in s["slot_leader"]]
    fra = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_fra.txt") if l.strip()}
    ams = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_ams.txt") if l.strip()}
    nf = np.array([u in fra for u in ids]); na = np.array([u in ams for u in ids])
    return LS0, lead, ids, nf, na


if __name__ == "__main__":
    t0 = time.time()
    os.makedirs(WORK, exist_ok=True)
    files = setup_run(); print("chunks", len(files), flush=True)
    pha = f"{WORK}/phaseA"
    if not os.path.exists(f"{WORK}/day_{TAG}.npz"):
        if not os.path.exists(f"{pha}/.done"):
            argv = sys.argv; sys.argv = [argv[0], RUN, pha]
            sys.path.insert(0, SELECT); import a_extract as A
            sys.argv = argv
            A.RUN = RUN; A.OUT = pha
            for b in range(A.NB): os.makedirs(os.path.join(pha, f"b{b:03d}"), exist_ok=True)
            tot = 0
            with Pool(PROCS) as p:
                for k, n in enumerate(p.imap_unordered(A.work, files), 1):
                    tot += n
                    if k % 20 == 0 or k == len(files): print(f"phase A {k}/{len(files)} {tot} txs {time.time() - t0:.0f}s", flush=True)
            open(f"{pha}/.done", "w").write("ok")
        sys.path.insert(0, PATTERNS); import p1_build as B
        B.TMP = f"{WORK}/tmp"; os.makedirs(B.TMP, exist_ok=True)
        B.D = M2; B.RUNS[TAG] = (os.path.basename(RUN), [pha])
        first = {}
        with Pool(PROCS) as p:
            for _, fs in p.imap_unordered(B.stage_a, [(TAG, b) for b in range(256)]):
                for u, k in fs.items():
                    if u not in first or k < first[u]: first[u] = k
        pickle.dump(first, open(f"{B.TMP}/{TAG}_first.pkl", "wb"), protocol=4)
        with Pool(PROCS, initializer=B.init_b, initargs=(TAG,)) as p:
            for _ in p.imap_unordered(B.stage_b, [(TAG, b) for b in range(256)]): pass
        po = B.PO; B.PO = WORK; nt = B.concat(TAG); B.PO = po
        print(f"day arrays: {nt} tokens {time.time() - t0:.0f}s", flush=True)
    import dd1_build as DB
    assert DB.SFX == "_s0.5", DB.SFX
    DB.DAYS[TAG] = WORK; DB.RUNDIR[TAG] = "../haqq_sel/m2/run_HQ"; DB.IMIT2[TAG] = []; DB.OUT = WORK
    DB.leader_map = leader_map
    os.makedirs(f"{WORK}/live", exist_ok=True)
    DB.main(TAG, PROCS)
    shutil.rmtree(pha, ignore_errors=True); shutil.rmtree(f"{WORK}/tmp", ignore_errors=True)
    print(f"done {time.time() - t0:.0f}s", flush=True)
