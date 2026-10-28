#!/usr/bin/env python3
"""hybrid step 1 (read-only): every live PRE-SEND fill (presend_live_close + _realized) of FRA r23-r28 and AMS r16-r34,
plus every pump.fun trade on those mints from the haqqml fresh tape (10-22 03:07 -> 10-28 20:45 PKT, all wallets),
extended for late AMS r34 fills with the local raw recorder chunks (run_20261028_1405, decoded).
Out: sniper-data/e2x1_dissect/hybrid/fills.pkl, tape.npz"""
import json, glob, gzip, pickle, sys, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import decode as D
OUT = "/home/moiz/sniper-data/e2x1_dissect/hybrid"; TP = "/home/moiz/sniper-data/haqqml/fresh/tape"
RUNS = [(f"FRA r{r}", f"/home/moiz/sniper-data/runs/fra/runs/dip_r{r}.jsonl") for r in (23, 24, 26, 27, 28)]
RUNS += [(f"AMS r{r}", f"/home/moiz/sniper-data/runs/ams/runs/dip_ams_r{r}.jsonl") for r in (16, 17, 19, 20, 24, 25, 26, 27)]
RUNS += [(f"AMS r{r}", f"{OUT}/ams_r{r}.jsonl") for r in range(28, 35)]
fills = []; shadow = []
W0, W1 = 1793118600, 1793205000   # last 24 h: 10-27 21:30 -> 10-28 21:30 PKT
for run, path in RUNS:
    close, real, rseq = [], {}, collections.defaultdict(list)
    for ln in open(path):
        if '"presend_' not in ln: continue
        d = json.loads(ln)
        if d["ev"] == "presend_live_close": close.append(d)
        elif d["ev"] == "presend_live_realized":
            if "buys" in d:
                for b in d["buys"]: real[b["sig"]] = d
            else: rseq[(d["mint"], d.get("w"), d.get("pid"))].append(d)
        elif d["ev"] == "presend_fill" and d.get("row") == "c" and W0 <= d["m"]["t"] / 1e9 <= W1:
            m = d["m"]; e = d["entry"]
            shadow.append(dict(run=run, mint=d["mint"], fs=m["slot"], fi=m["idx"], fj=m["j"], ft=m["t"] / 1e9, tokens=e["tokens"], sol_in=e["sol_in"],
                               vs0=e["vsol"], vt0=e["vtok"], w=d.get("w"), fired=d.get("imit", {}).get("fired"), drop=d.get("drop_pct")))
    for c in close:
        rz = real.get(c["buy_sig"])
        if rz is None and rseq.get((c["mint"], c.get("w"), c.get("pid"))): rz = rseq[(c["mint"], c.get("w"), c.get("pid"))].pop(0)
        sl = c.get("sell_lands") or [c["sell_land"]]
        fills.append(dict(run=run, mint=c["mint"], buy_sig=c["buy_sig"], fs=c["land"][0], fi=c["land"][1], ft=c["land"][2] / 1e9,
                          tokens=c["tokens"], sol_in=c["sol_in_curve"], sells=[tuple(x[:4]) for x in sl], sold=sum(x[3] for x in sl),
                          exit_why=c["exit_why"], held_s=c["held_s"], curve_pnl=c["curve_pnl"] / 1e9,
                          real=(rz["pnl"] / 1e9 if rz else None), result=c["result"]))
print("fills", len(fills), collections.Counter(f["run"] for f in fills))
mints = json.load(open(f"{TP}/mints.json")); mid = {m: i for i, m in enumerate(mints)}
want = sorted({mid[f["mint"]] for f in fills + shadow if f["mint"] in mid})
print("shadow", len(shadow), collections.Counter(f["run"] for f in shadow))
print("mints", len({f['mint'] for f in fills}), "in tape", len(want))
T = np.load(f"{TP}/trades.npy", mmap_mode="r")
mc = np.asarray(T["mint"]); keep = np.flatnonzero(np.isin(mc, np.array(want, dtype=mc.dtype)))
cols = ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "rsol", "rtok", "bt")
c = {k: np.asarray(T[k][keep]) for k in cols}
users = json.load(open(f"{TP}/users.json"))
c["mint"] = np.array([mints[x] for x in c["mint"]], dtype=object); c["user"] = np.array([users[x] for x in c["user"]], dtype=object)
TEND = int(c["slot"].max()) if len(keep) else 0
print("tape rows", len(keep), "tape end slot", int(np.load(f"{TP}/slots.npy", mmap_mode='r')["slot"][-1]))
# extension: raw recorder chunks after the fresh tape end (late AMS r34 fills)
SEND = int(np.load(f"{TP}/slots.npy", mmap_mode='r')["slot"][-1])
late = {f["mint"] for f in fills + shadow if f["ft"] > 1793202316 - 1900}
ext = []
if late:
    import subprocess
    open(f"{OUT}/late_mints.txt", "w").write("\n".join(sorted(late)) + "\n")
    loc = sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261028_1405/txs/*.jsonl.gz"))
    lastloc = max(int(x.split("_")[-1].split(".")[0]) for x in loc); loc = loc[:-1]   # last local chunk may still be syncing: read it on the server
    subprocess.run(["scp", "-q", "-P", "1996", f"{OUT}/late_mints.txt", "it@84.32.100.36:/tmp/hybrid_late_mints.txt"])
    cmd = (f"cd /root/sniper-collect/run_20261028_1405/txs 2>/dev/null; for f in $(sudo ls /root/sniper-collect/run_20261028_1405/txs/); do t=${{f#txs_}}; t=${{t%.jsonl.gz}}; "
           f"[ $t -ge {lastloc} ] && sudo sh -c \"zcat /root/sniper-collect/run_20261028_1405/txs/$f 2>/dev/null\" | grep -F -f /tmp/hybrid_late_mints.txt; done")
    rem = subprocess.run(["ssh", "-p", "1996", "it@84.32.100.36", cmd], capture_output=True, text=True).stdout.splitlines()
    print("server ext lines", len(rem))
    def lines():
        for fn in loc:
            try:
                for line in gzip.open(fn, "rt"): yield line
            except EOFError: print("truncated", fn)
        yield from rem
    if True:
        for line in lines():
            if not any(m in line for m in late): continue
            try: d = json.loads(line)
            except Exception: continue
            if d.get("err") is not None or d["s"] <= SEND: continue
            signer = (d.get("signers") or [None])[0]
            for j, b in enumerate(D.chunks_of(d.get("ev"))):
                if b[:8] != D.DISC: continue
                p = D.parse_trade(b)
                if p and p[0] in late:
                    ext.append((d["s"], d["i"], j, p[0], p[4] if len(p) > 4 and isinstance(p[4], str) else signer, int(p[3]), p[1], p[2], p[5], p[6], 0, 0, d.get("bt", 0)))
    print("ext rows", len(ext))
if ext:
    for n, k in enumerate(cols): c[k] = np.concatenate([c[k], np.array([r[n] for r in ext], dtype=c[k].dtype)])
o = np.lexsort((c["j"], c["idx"], c["slot"]))
c = {k: v[o] for k, v in c.items()}
pickle.dump(dict(fills=fills, shadow=shadow, tape=c, tape_end_slot=max(SEND, max([r[0] for r in ext], default=0))), open(f"{OUT}/build.pkl", "wb"))
print("saved")
