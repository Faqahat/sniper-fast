import os, json, time, sys, urllib.request, urllib.error, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
CAP = 100
THRESH = 30

def rpc(m, p, tries=8):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as r:
                j = json.loads(r.read())
            if "error" in j:
                time.sleep(0.3 * (t + 1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            time.sleep(1.0 + 0.8 * t if getattr(e, "code", 0) == 429 else 0.4 * (t + 1))
        except Exception:
            time.sleep(0.4 * (t + 1))
    return None

def nsigs(creator):
    r = rpc("getSignaturesForAddress", [creator, {"limit": CAP}])
    if r is None:
        return (creator, -1)
    return (creator, len(r))

def pct(a, q):
    if not a:
        return None
    i = min(len(a) - 1, int(q * len(a)))
    return a[i]

def main():
    d = json.load(open("/root/creators_resolved.json"))
    picks = {m: c for m, c in d["picks"].items() if c}
    pop = {m: c for m, c in d["pop"].items() if c}
    pick_creators = set(picks.values())
    pop_creators = set(pop.values())
    allc = sorted(pick_creators | pop_creators)
    print(f"unique creators to count: {len(allc)} (picks={len(pick_creators)} pop={len(pop_creators)})", file=sys.stderr)

    counts = {}
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs = {ex.submit(nsigs, c): c for c in allc}
        done = 0
        for f in as_completed(futs):
            c, n = f.result(); counts[c] = n; done += 1
            if done % 300 == 0:
                print(f"  count {done}/{len(allc)}", file=sys.stderr)
    json.dump(counts, open("/root/creator_sigcounts.json", "w"))

    # blocklist: n > THRESH (serial). exclude rpc failures (-1)
    blocked = sorted(c for c, n in counts.items() if n > THRESH)
    with open("/root/sniper-fast/creator_blocklist.txt", "w") as f:
        for c in blocked:
            f.write(c + "\n")

    # distribution over population creators
    popvals = sorted(counts[c] for c in pop_creators if counts.get(c, -1) >= 0)
    med = statistics.median(popvals) if popvals else None
    print("==== DISTRIBUTION (population creators prior_sigs, capped at 100) ====")
    print(f"pop creators measured: {len(popvals)}")
    print(f"median={med} p25={pct(popvals,0.25)} p75={pct(popvals,0.75)} p90={pct(popvals,0.90)} p99={pct(popvals,0.99)} max(cap)={max(popvals) if popvals else None}")
    buckets = {"0": 0, "1-5": 0, "6-30": 0, "31-99": 0, "100+(cap)": 0}
    for n in popvals:
        if n == 0: buckets["0"] += 1
        elif n <= 5: buckets["1-5"] += 1
        elif n <= 30: buckets["6-30"] += 1
        elif n < 100: buckets["31-99"] += 1
        else: buckets["100+(cap)"] += 1
    print("buckets:", buckets)

    pop_blocked = sum(1 for c in pop_creators if counts.get(c, -1) > THRESH)
    print(f"pop creators blocklisted (>{THRESH}): {pop_blocked}/{len(pop_creators)}")
    print(f"TOTAL blocklist size (picks+pop union): {len(blocked)}")

    # ===== VALIDATION: fraction of 4yFAz picks wrongly blocked =====
    blockset = set(blocked)
    pick_vals = sorted(counts[c] for c in pick_creators if counts.get(c, -1) >= 0)
    pmed = statistics.median(pick_vals) if pick_vals else None
    pick_mints_blocked = sum(1 for m, c in picks.items() if c in blockset)
    pick_mints_total = len(picks)
    pc_measured = [c for c in pick_creators if counts.get(c, -1) >= 0]
    pc_blocked = sum(1 for c in pc_measured if counts[c] > THRESH)
    print("==== VALIDATION vs 4yFAz picks ====")
    print(f"picks creators measured: {len(pc_measured)}  median prior_sigs={pmed} p90={pct(pick_vals,0.90)}")
    print(f"picks creators blocked: {pc_blocked}/{len(pc_measured)} = {100*pc_blocked/max(1,len(pc_measured)):.1f}%")
    print(f"picks MINTS blocked: {pick_mints_blocked}/{pick_mints_total} = {100*pick_mints_blocked/max(1,pick_mints_total):.1f}%")
    print(f"failures(rpc -1): pop={sum(1 for c in pop_creators if counts.get(c)==-1)} picks={sum(1 for c in pick_creators if counts.get(c)==-1)}")

if __name__ == "__main__":
    main()
