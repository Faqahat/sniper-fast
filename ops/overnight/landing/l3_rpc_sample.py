#!/usr/bin/env python3
# LANDING-PATH STUDY, step 3 (READ-ONLY RPC, getTransaction only, <= 6 req/s, ~1,400 requests).
# Fetch a sample of txs to see what the collector does not keep:
#   - durable nonce (first instruction = System AdvanceNonceAccount), tx version (legacy / 0 / 1),
#   - the tip accounts named in the message (also for FAILED txs, whose tip transfer reverted and so is not in the
#     balance deltas) and the tip lamports from the System transfer instruction data.
# Samples: A) 2 OK buys from each of the top-80 repeat snipers (by create-slot share), B) 500 random OK buys,
#          C) 400 random failed buy-instruction txs + 300 random failed no-instruction txs (guard fails).
#          D) (mode 'fanout') up to 3 OK buys from every wallet whose landed buys switch between single-service paths.
# The RPC URL is read from ~/.config/sniper/ck_rpc_url and is never printed or written.
# usage: python3 -I l3_rpc_sample.py            (samples A-C)
#        python3 -I l3_rpc_sample.py fanout     (sample D)
import os, json, gzip, time, random, collections, urllib.request

W = "/home/moiz/sniper/ops/overnight/landing/work"
URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TIPMAP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
OUTF = os.path.join(W, "rpc/txsample.jsonl")


def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b


def svc(a):
    return TIPMAP.get(a) or ("nozomi" if a.startswith("noz") else None)


_last = [0.0]


def rpc(method, params, tries=4):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for k in range(tries):
        w = _last[0] + 1 / 6.0 - time.time()
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(URL, data=body, headers={"content-type": "application/json"}), timeout=30))
            if "error" in r:
                time.sleep(1 + k); continue
            return r.get("result")
        except Exception as e:
            print("exception", type(e).__name__, flush=True)
            time.sleep(1 + 2 * k)
    return None


def summarize(sig, t):
    msg = t["transaction"]["message"]; meta = t.get("meta") or {}
    keys = list(msg.get("accountKeys") or [])
    la = meta.get("loadedAddresses") or {}
    allk = keys + la.get("writable", []) + la.get("readonly", [])
    ixs = msg.get("instructions") or []
    first_prog = allk[ixs[0]["programIdIndex"]] if ixs and ixs[0]["programIdIndex"] < len(allk) else None
    nonce = False
    tips = []
    has_cb = False
    for n, ix in enumerate(ixs):
        p = allk[ix["programIdIndex"]] if ix["programIdIndex"] < len(allk) else None
        try: d = b58dec(ix.get("data") or "")
        except Exception: d = b""
        if p == CB: has_cb = True
        if p == SYS:
            if n == 0 and d[:4] == b"\x04\x00\x00\x00": nonce = True
            if d[:4] == b"\x02\x00\x00\x00" and len(d) >= 12 and len(ix.get("accounts") or []) >= 2:
                to = allk[ix["accounts"][1]]
                if svc(to): tips.append([svc(to), to, int.from_bytes(d[4:12], "little")])
    # inner instructions too (router programs that pay the tip by CPI)
    for inn in meta.get("innerInstructions") or []:
        for ix in inn.get("instructions") or []:
            p = allk[ix["programIdIndex"]] if ix["programIdIndex"] < len(allk) else None
            if p != SYS: continue
            try: d = b58dec(ix.get("data") or "")
            except Exception: continue
            if d[:4] == b"\x02\x00\x00\x00" and len(d) >= 12 and len(ix.get("accounts") or []) >= 2:
                to = allk[ix["accounts"][1]]
                if svc(to): tips.append([svc(to), to, int.from_bytes(d[4:12], "little"), "cpi"])
    tip_keys = sorted({svc(a) for a in allk if svc(a)})
    return dict(sig=sig, ver=t.get("version"), nonce=nonce, first_prog=first_prog, nix=len(ixs), has_cb=has_cb, tips=tips,
                tip_keys=tip_keys, err=meta.get("err") is not None, fee=meta.get("fee"), nsig=(msg.get("header") or {}).get("numRequiredSignatures"),
                slot=t.get("slot"))


def fanout_jobs(B):
    # extra sample: 2 OK buys from every wallet with >=15 launches whose landed buys use >=2 single-service paths
    by_w = collections.defaultdict(list)
    for b in B: by_w[b["payer"]].append(b)
    jobs = []
    for w, v in by_w.items():
        if len({x["mint"] for x in v}) < 15: continue
        single = [b for b in v if b["path"] != "none" and not b["path"].startswith("multi:")]
        pm = collections.Counter(b["path"] for b in single)
        if len(single) < 15 or len(pm) < 2 or pm.most_common(1)[0][1] > 0.9 * len(single): continue
        v2 = sorted(single, key=lambda x: (x["s"], x["i"]))
        picks = {v2[0]["sig"], v2[len(v2) // 2]["sig"], v2[-1]["sig"]}
        for s in sorted(picks): jobs.append(("D_fan", s))
    return jobs


def main():
    random.seed(20261023)
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "fanout":
        B = [json.loads(l) for l in gzip.open(os.path.join(W, "rows_buys.jsonl.gz"), "rt")]
        return run(fanout_jobs(B))
    B = [json.loads(l) for l in gzip.open(os.path.join(W, "rows_buys.jsonl.gz"), "rt")]
    F = [json.loads(l) for l in gzip.open(os.path.join(W, "rows_fail.jsonl.gz"), "rt")]
    by_w = collections.defaultdict(list)
    for b in B: by_w[b["payer"]].append(b)
    rep = [(w, v) for w, v in by_w.items() if len({x["mint"] for x in v}) >= 15]
    rep.sort(key=lambda wv: -sum(1 for x in wv[1] if x["d"] == 0) / len(wv[1]))
    jobs = []
    for w, v in rep[:80]:
        v2 = sorted(v, key=lambda x: (x["d"], x["s"]))
        for x in [v2[0], v2[len(v2) // 2]]: jobs.append(("A_top", x["sig"]))
    for x in random.sample(B, 500): jobs.append(("B_ok", x["sig"]))
    fb = [f for f in F if f["buyix"]]; fn = [f for f in F if f["noix"]]
    for x in random.sample(fb, 400): jobs.append(("C_failbuy", x["sig"]))
    for x in random.sample(fn, 300): jobs.append(("C_failnoix", x["sig"]))
    run(jobs)


def run(jobs):
    done = set()
    if os.path.exists(OUTF):
        for l in open(OUTF):
            try: done.add(json.loads(l)["sig"])
            except Exception: pass
    print("jobs", len(jobs), "already", len(done), flush=True)
    n = 0
    with open(OUTF, "a") as fo:
        for grp, sig in jobs:
            if sig in done: continue
            t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
            if not t:
                fo.write(json.dumps(dict(sig=sig, grp=grp, missing=True)) + "\n"); continue
            try: s = summarize(sig, t)
            except Exception as e:
                s = dict(sig=sig, parse_error=type(e).__name__)
            s["grp"] = grp
            fo.write(json.dumps(s, separators=(",", ":")) + "\n"); done.add(sig); n += 1
            if n % 100 == 0:
                fo.flush(); print("fetched", n, flush=True)
    print("RPC SAMPLE DONE", n, flush=True)


if __name__ == "__main__":
    main()
