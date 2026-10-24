#!/usr/bin/env python3
# Claim 3a: with DIP_HLAG=0, does dipbuy5 produce exactly dipbuy4's rows? Full check over ALL buckets (the claim checked 453 rows
# in 6 buckets). Both modules are the snapshot copies (v2_mods/*_s.py, slip limits from the frozen V2_SLIP file) and share the
# same launch list, so data or slip-file growth cannot create differences. Row = every field except dipbuy5's extra "kv_lag".
# env (same as the claim's ev_hlag0 build): RP_PHASEA_R2=phaseA_dry SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5
#      DIP_HS=2 DIP_BUSY=5 DIP_HLAG=0 V2_SLIP=v2_snap/slip_args_snap.jsonl
import sys, os, json, collections
from multiprocessing import Pool
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_mods"))
import dipbuy4_s as A
import dipbuy5_s as B
B.L = A.L; B.byb = A.byb
def one(key):
    ra, _ = A.work(key); rb, _ = B.work(key)
    same = diff = 0; fields = collections.Counter()
    for x, y in zip(ra, rb):
        y = dict(y); y.pop("kv_lag", None)
        if json.dumps(x, sort_keys=True) == json.dumps(y, sort_keys=True): same += 1
        else:
            diff += 1
            for k in set(x) | set(y):
                if json.dumps(x.get(k), sort_keys=True) != json.dumps(y.get(k), sort_keys=True): fields[k] += 1
    return key, len(ra), len(rb), same, diff, fields
if __name__ == "__main__":
    assert os.environ.get("DIP_HLAG", "0") == "0"
    tot = collections.Counter(); F = collections.Counter(); mism = []
    with Pool(int(os.environ.get("NPROC", "6"))) as p:
        for key, na, nb, s, d, f in p.imap_unordered(one, sorted(A.byb), chunksize=2):
            tot["rows_a"] += na; tot["rows_b"] += nb; tot["same"] += s; tot["diff"] += d; F.update(f)
            if na != nb: mism.append((key, na, nb))
    print("buckets", len(A.byb), dict(tot), "length mismatches", mism[:10], "fields differing", dict(F))
