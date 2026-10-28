#!/usr/bin/env python3
"""FRONT step 6 (read-only): tx shape of the dump and of the first buys after it, on the paying set S vs the control set C.
Shape per landed tx (raw recordings): landing service(s) from tip accounts (work/tipmap.json; 'notip' if none), Jito tip y/n, CU
price, fee, CU limit, durable nonce (AdvanceNonce/ValidateNonce ix), router program (first non-standard program), signer.
Out: sniper-data/haqq_dissect/front/f6.pkl (per dump: dump shape + front shapes) and f6_shape.txt (tables)"""
import json, glob, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
       "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo",
       "SysvarRent111111111111111111111111111111111", "SysvarC1ock11111111111111111111111111111111"}


def shape(d):
    tips = d.get("tips") or []
    paths = sorted({TIP.get(k, "nozomi" if k.startswith("noz") else "?" + k[:5]) for k, _ in tips}) or ["notip"]
    ixn = d.get("ixn") or []
    rp = [p for p in (d.get("progs") or []) if p not in STD]
    return dict(paths=paths, jito=any(TIP.get(k) == "jito" for k, _ in tips), tip=sum(x for _, x in tips), cup=d.get("cup"), cul=d.get("cul"), fee=d.get("fee"),
                cu=d.get("cu"), nonce=any(x in ("AdvanceNonceAccount", "ValidateNonce") for x in ixn), router=rp[0][:8] if rp else "direct",
                signer=d["signers"][0], sig=d["sig"], err=d.get("err") is not None, nsig=len(d.get("signers") or []))


def load_raw():
    X = {}
    for f in glob.glob(f"{OUT}/raw/*.jsonl"):
        for l in open(f):
            try: d = json.loads(l)
            except Exception: continue
            X[(d["s"], d["i"])] = d
    return X


def main():
    R = pickle.load(open(f"{OUT}/f1.pkl", "rb")); SE = pickle.load(open(f"{OUT}/f2_sets.pkl", "rb"))
    F4 = {(x["set"], x["i"]): x for x in pickle.load(open(f"{OUT}/f4.pkl", "rb"))}
    X = load_raw()
    print(f"raw records {len(X):,}", flush=True)
    rows = []
    for setname in ("S", "C"):
        for i in SE[setname]:
            r = R[i]; d = X.get((r["ds"], r["di"]))
            if d is None: continue
            fr = []
            for f in r["front"][:6 if setname == "S" else 3]:
                x = X.get((f["slot"], f["idx"]))
                fr.append(dict(f, shape=shape(x) if x else None))
            j = F4[(setname, i)]
            rows.append(dict(set=setname, i=i, dump=shape(d), front=fr, client=j["client"], region=j["region"], raw_client=j["raw_client"], day=j["day"],
                             vpos=r["front"][0].get("vpos"), vf=r["vf"]))
    pickle.dump(rows, open(f"{OUT}/f6.pkl", "wb"))
    out = []
    def P(*a): s = " ".join(str(x) for x in a); print(s); out.append(s)
    S = [x for x in rows if x["set"] == "S"]; C = [x for x in rows if x["set"] == "C"]
    P(f"# Tx shape at the front (MEASURED, raw recordings). S = paying dumps with shape data: {len(S):,}; C = crowded non-paying control: {len(C):,}")
    def tab(title, grp, k):
        sh = [x["front"][k]["shape"] for x in grp if len(x["front"]) > k and x["front"][k]["shape"]]
        if not sh: return
        pc = collections.Counter(p for s in sh for p in s["paths"]); n = len(sh)
        cup = np.array([s["cup"] for s in sh if s["cup"]]); fee = np.array([s["fee"] for s in sh])
        P(f"\n## {title}: buyer #{k+1}, n {n:,}")
        P(f"- services (share of txs paying each; a tx can pay several): " + ", ".join(f"{p} {100*c/n:.1f}%" for p, c in pc.most_common(12)))
        P(f"- Jito tip {100*np.mean([s['jito'] for s in sh]):.1f}%; durable nonce {100*np.mean([s['nonce'] for s in sh]):.1f}%; own router program "
          f"{100*np.mean([s['router'] != 'direct' for s in sh]):.1f}%; CU price p25/p50/p75 {np.percentile(cup,25):,.0f}/{np.median(cup):,.0f}/{np.percentile(cup,75):,.0f} "
          f"(n {len(cup):,}); fee p50 {np.median(fee)/1e9*1e3:.3f} mSOL, p90 {np.percentile(fee,90)/1e9*1e3:.3f}; tip p50 {np.median([s['tip'] for s in sh])/1e6:.3f} mSOL")
    for k in range(3):
        tab("PAYING (S)", S, k)
        tab("CONTROL (C)", C, k)
    # by client: front1 service mix
    P("\n## Front buyer #1 on paying dumps, by leader client: top services and Jito-tip share")
    for cl in ("bam", "harmonic", "jito", "fd", "agave", "other"):
        sh = [x["front"][0]["shape"] for x in S if x["client"] == cl and x["front"] and x["front"][0]["shape"]]
        if len(sh) < 30: continue
        pc = collections.Counter(p for s in sh for p in s["paths"]); n = len(sh)
        P(f"- {cl} (n {n:,}): " + ", ".join(f"{p} {100*c/n:.0f}%" for p, c in pc.most_common(8)) + f"; Jito tip {100*np.mean([s['jito'] for s in sh]):.0f}%; "
          f"CU price p50 {np.median([s['cup'] for s in sh if s['cup']] or [0]):,.0f}")
    open(f"{OUT}/f6_shape.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
