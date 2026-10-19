#!/usr/bin/env python3
"""PRE-CREATE feature extraction. For each launch (his picks + unbiased population),
look at the creator wallet history in the window BEFORE the create slot and extract:
 - fund_recency_slots : create_slot - slot of the most recent SOL inflow to creator before create
 - fund_amount        : SOL of that inflow
 - fund_src           : sender wallet of that inflow
 - prior_n            : creator pre-create tx count (capped, activity proxy)
 - gap_since_last     : create_slot - most recent prior activity slot
 - first_seen_slot    : oldest sig slot in window (account-age proxy; only if page not full)
Outcome + serial-launcher + shared-funder + density are joined in the analysis step.
Reuses common.py (RPC, gettx, b58). getSignaturesForAddress is disk-cached per (addr,before)."""
import os, sys, json, threading, queue
sys.path.insert(0, "/root/profit_backtest")
import common
from common import rpc, gettx, _keys

CACHE_SIG = "/root/precreate/sigcache"
os.makedirs(CACHE_SIG, exist_ok=True)
LAM = 1e9
FUND_MIN_SOL = 0.01          # min inflow to count as a funding event
SCAN_TXS = 14                # how many most-recent pre-create txs to fetch looking for the inflow


def sigs_for(addr, before=None, limit=1000):
    key = "%s_%s_%s" % (addr, before or "head", limit)
    f = os.path.join(CACHE_SIG, key + ".json")
    if os.path.exists(f):
        try:
            return json.load(open(f))
        except Exception:
            pass
    pr = [addr, {"limit": limit}]
    if before:
        pr[1]["before"] = before
    r = rpc("getSignaturesForAddress", pr) or []
    try:
        json.dump(r, open(f, "w"))
    except Exception:
        pass
    return r


def creator_delta(tx, creator):
    """lamport delta for creator in this tx, and the biggest sender (most negative delta) acct."""
    if not tx or not tx.get("meta"):
        return None, None
    meta = tx["meta"]
    keys = _keys(tx)
    if creator not in keys:
        return None, None
    ci = keys.index(creator)
    pre = meta["preBalances"]
    post = meta["postBalances"]
    if ci >= len(pre):
        return None, None
    d = (post[ci] - pre[ci]) / LAM
    best_src = None
    best_neg = 0.0
    for i, k in enumerate(keys):
        if i == ci or i >= len(pre):
            continue
        dd = (post[i] - pre[i]) / LAM
        if dd < best_neg:
            best_neg = dd
            best_src = k
    return d, best_src


def get_create_sig(creator, create_slot):
    """find the create sig to anchor the pre-create window. Page creator history until we
    reach create_slot. Returns (create_sig_or_None, prior_sigs_strictly_before_create)."""
    before = None
    for _page in range(5):
        chunk = sigs_for(creator, before=before, limit=1000)
        if not chunk:
            return None, []
        idx_cross = None
        for i, s in enumerate(chunk):
            if s["slot"] <= create_slot:
                idx_cross = i
                break
        if idx_cross is not None:
            cross = chunk[idx_cross]
            csig = cross["signature"] if cross["slot"] == create_slot else None
            prior = [s for s in chunk[idx_cross:] if s["slot"] < create_slot]
            if len(prior) < SCAN_TXS and len(chunk) == 1000:
                more = sigs_for(creator, before=chunk[-1]["signature"], limit=1000)
                prior += [s for s in more if s["slot"] < create_slot]
            return csig, prior
        before = chunk[-1]["signature"]
        if len(chunk) < 1000:
            break
    return None, []


def extract_one(rec):
    creator = rec["creator"]
    create_slot = rec["create_slot"]
    out = {"mint": rec["mint"], "creator": creator, "create_slot": create_slot, "is_his": rec["is_his"]}
    try:
        csig, prior = get_create_sig(creator, create_slot)
        out["create_sig_found"] = csig is not None
        out["prior_n"] = len(prior)
        if prior:
            out["gap_since_last"] = create_slot - prior[0]["slot"]
            out["first_seen_slot"] = prior[-1]["slot"]
        else:
            out["gap_since_last"] = None
            out["first_seen_slot"] = None
        fr = fa = fsrc = None
        for s in prior[:SCAN_TXS]:
            tx = gettx(s["signature"])
            d, src = creator_delta(tx, creator)
            if d is not None and d >= FUND_MIN_SOL:
                fr = create_slot - s["slot"]
                fa = d
                fsrc = src
                break
        out["fund_recency_slots"] = fr
        out["fund_amount"] = fa
        out["fund_src"] = fsrc
        out["fund_found"] = fr is not None
    except Exception as e:
        out["err"] = str(e)
    return out


def main():
    SAMPLE = json.load(open("/root/precreate/sample.json"))
    print("extracting pre-create features for %d launches" % len(SAMPLE), flush=True)
    results = [None] * len(SAMPLE)
    lock = threading.Lock()
    done = [0]
    q = queue.Queue()
    for i in range(len(SAMPLE)):
        q.put(i)

    def run():
        while True:
            try:
                i = q.get_nowait()
            except Exception:
                return
            results[i] = extract_one(SAMPLE[i])
            with lock:
                done[0] += 1
                if done[0] % 50 == 0:
                    print("  %d/%d" % (done[0], len(SAMPLE)), flush=True)
            q.task_done()

    threads = [threading.Thread(target=run) for _ in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    json.dump(results, open("/root/precreate/precreate_raw.json", "w"))
    nf = sum(1 for r in results if r and r.get("fund_found"))
    print("done. fund_found %d/%d" % (nf, len(results)), flush=True)


if __name__ == "__main__":
    main()
