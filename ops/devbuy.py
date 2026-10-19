import os, json, time, urllib.request, urllib.error, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL = "So11111111111111111111111111111111111111112"
TARGET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
RENT = 1_461_600  # bonding curve rent-exempt min lamports

def rpc(method, params, tries=5):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last = None
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                j = json.loads(r.read())
            if "error" in j:
                last = j["error"]
                time.sleep(0.3*(t+1)); continue
            return j.get("result")
        except Exception as e:
            last = e
            time.sleep(0.4*(t+1))
    raise RuntimeError(f"rpc fail {method}: {last}")

def get_sigs_all(addr, want, oldest=False):
    """Page getSignaturesForAddress. If oldest, keep paging to end and return all."""
    out = []
    before = None
    while True:
        params = [addr, {"limit":1000}]
        if before: params[1]["before"] = before
        res = rpc("getSignaturesForAddress", params)
        if not res: break
        out.extend(res)
        before = res[-1]["signature"]
        if not oldest and len(out) >= want: break
        if len(res) < 1000: break
    return out

def get_tx(sig):
    return rpc("getTransaction", [sig, {"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])

def is_pump_buy(tx):
    if not tx or tx.get("meta",{}).get("err") is not None: return False
    logs = tx.get("meta",{}).get("logMessages") or []
    inpump = any(PUMP in l for l in logs)
    if not inpump: return False
    txt = " ".join(logs)
    return ("Instruction: Buy" in txt) or ("BuyExactQuote" in txt) or ("Instruction: ExtendAccount" in txt and False)

def buy_mint(tx):
    """mint that target's token balance increased for."""
    meta = tx.get("meta",{})
    pre = {(b["owner"],b["mint"]):float(b["uiTokenAmount"]["amount"]) for b in meta.get("preTokenBalances",[])}
    best=None;bestd=0
    for b in meta.get("postTokenBalances",[]):
        if b.get("owner")!=TARGET: continue
        if b["mint"]==WSOL: continue
        post=float(b["uiTokenAmount"]["amount"])
        d=post-pre.get((TARGET,b["mint"]),0.0)
        if d>bestd: bestd=d; best=b["mint"]
    return best

def dev_buy_from_create(mint, create_tx):
    """Find bonding curve account (owned by pump) and its lamport increase, minus rent."""
    meta = create_tx.get("meta",{})
    msg = create_tx["transaction"]["message"]
    keys = msg.get("accountKeys",[])
    # account pubkeys in order
    pubs = [k["pubkey"] if isinstance(k,dict) else k for k in keys]
    pre = meta.get("preBalances",[])
    post = meta.get("postBalances",[])
    # identify bonding curve: account owned by PUMP (post state) with lamports increase
    # we only know owners of token accounts from postTokenBalances; bonding curve is a program-owned PDA.
    # Use: find account whose lamport delta is largest positive and is NOT a token program etc.
    # Better: bonding curve PDA holds the token supply -> appears in postTokenBalances with owner==PUMP? no, owner is the curve itself.
    # Approach: the curve account's owner (account-level) is PUMP. We don't have account owners here except via separate query.
    # Fallback practical: the account (not fee payer idx0) with the largest positive lamport delta in a create tx is the bonding curve.
    deltas = []
    for i,p in enumerate(pubs):
        if i < len(pre) and i < len(post):
            deltas.append((post[i]-pre[i], i, p))
    # exclude fee payer (idx0, net negative anyway)
    pos = sorted([d for d in deltas if d[0]>0], reverse=True)
    result = {}
    # candidate bonding curve = largest positive lamport gain
    if pos:
        gain, idx, pub = pos[0]
        result["curve_gain_lamports"] = gain
        result["curve_pub"] = pub
        result["dev_buy_lamports_curve"] = gain - RENT
    # fallback: fee payer net spent minus fee
    fee = meta.get("fee",0)
    payer_spent = (pre[0]-post[0]) if pre and post else 0
    result["payer_net_spent_lamports"] = payer_spent - fee
    result["fee_payer"] = pubs[0] if pubs else None
    return result

def main():
    want_mints = 200
    print("fetching target sigs...", file=sys.stderr)
    sigs = get_sigs_all(TARGET, 6000)  # grab plenty; many are sells/other
    sigs = [s for s in sigs if s.get("err") is None]
    print(f"landed sigs: {len(sigs)}", file=sys.stderr)

    # fetch txs in parallel, find buys, collect unique mints in recency order
    mints = []
    seen = set()
    sig_list = [s["signature"] for s in sigs]

    def work(sig):
        try:
            tx = get_tx(sig)
            if is_pump_buy(tx):
                m = buy_mint(tx)
                return (sig, m)
        except Exception as e:
            return (sig, None)
        return (sig, None)

    results = {}
    with ThreadPoolExecutor(max_workers=30) as ex:
        futs = {ex.submit(work, s): s for s in sig_list}
        for f in as_completed(futs):
            sig, m = f.result()
            results[sig] = m

    # preserve recency order (sig_list already newest-first)
    for sig in sig_list:
        m = results.get(sig)
        if m and m not in seen:
            seen.add(m); mints.append(m)
        if len(mints) >= want_mints: break

    print(f"unique bought mints: {len(mints)}", file=sys.stderr)

    # for each mint find create tx = oldest signature
    def resolve_create(mint):
        try:
            allsigs = get_sigs_all(mint, 0, oldest=True)
            if not allsigs: return (mint, None, "no_sigs")
            oldest_sig = allsigs[-1]["signature"]
            ctx = get_tx(oldest_sig)
            if not ctx: return (mint, None, "no_ctx")
            meta = ctx.get("meta",{})
            msg = ctx["transaction"]["message"]
            pubs = [k["pubkey"] if isinstance(k,dict) else k for k in msg.get("accountKeys",[])]
            pre = meta.get("preBalances",[]); post = meta.get("postBalances",[])
            logs = meta.get("logMessages") or []
            # confirm PUMP-owned bonding-curve account with largest positive lamport gain
            gm = rpc("getMultipleAccounts",[pubs,{"encoding":"base64"}])
            best=None  # (gain, idx, pub)
            for i,acc in enumerate(gm.get("value") or []):
                if acc and acc.get("owner")==PUMP and i < len(pre) and i < len(post):
                    gain = post[i]-pre[i]
                    if gain>0 and (best is None or gain>best[0]):
                        best=(gain,i,pubs[i])
            info = {"create_sig":oldest_sig,"n_sigs":len(allsigs),
                    "has_create_log": any("Instruction: Create" in l for l in logs)}
            if best:
                info["curve_pub"]=best[2]; info["curve_gain_lamports"]=best[0]
                info["dev_buy_lamports"]=best[0]-RENT
                info["dev_buy_sol"]=(best[0]-RENT)/1e9
            else:
                # fallback: fee payer net spent minus fee
                fee=meta.get("fee",0)
                sp=(pre[0]-post[0]-fee) if pre and post else 0
                info["dev_buy_lamports"]=sp; info["dev_buy_sol"]=sp/1e9; info["fallback"]=True
            return (mint, info, "ok")
        except Exception as e:
            return (mint, None, f"err:{e}")

    resolved = {}
    with ThreadPoolExecutor(max_workers=25) as ex:
        futs = {ex.submit(resolve_create, m): m for m in mints}
        for f in as_completed(futs):
            mint, info, status = f.result()
            resolved[mint] = (info, status)

    # dump raw
    with open("/root/devbuy_raw.json","w") as fh:
        json.dump({m:(resolved[m][0], resolved[m][1]) for m in mints}, fh, indent=0)

    ok = [(m,resolved[m][0]) for m in mints if resolved[m][1]=="ok" and resolved[m][0]]
    fails = [(m,resolved[m][1]) for m in mints if not (resolved[m][1]=="ok" and resolved[m][0])]
    print(f"resolved ok: {len(ok)} / {len(mints)}  fails: {len(fails)}", file=sys.stderr)

    vals = sorted(info["dev_buy_sol"] for m,info in ok if info.get("dev_buy_sol") is not None)
    import statistics as st
    def pct(a,q):
        if not a: return None
        i=(len(a)-1)*q; lo=int(i); hi=min(lo+1,len(a)-1)
        return a[lo]+(a[hi]-a[lo])*(i-lo)
    # cleaned = drop non-positive / absurd (>50 SOL)
    clean=[v for v in vals if 0 < v < 50]
    dropped=[v for v in vals if not (0 < v < 50)]

    def report(a,label):
        if not a:
            print(f"\n[{label}] empty"); return
        print(f"\n[{label}] n={len(a)}")
        print(f"  min={a[0]:.3f} p10={pct(a,.1):.3f} p25={pct(a,.25):.3f} median={st.median(a):.3f} p75={pct(a,.75):.3f} p90={pct(a,.9):.3f} max={a[-1]:.3f} mean={st.mean(a):.3f} SOL")
        for usd in (180,220):
            print(f"  median ${st.median(a)*usd:.0f} | p25-p75 ${pct(a,.25)*usd:.0f}-${pct(a,.75)*usd:.0f} | p10-p90 ${pct(a,.1)*usd:.0f}-${pct(a,.9)*usd:.0f}  (@${usd}/SOL)")
        # histogram 0.25 buckets
        from collections import Counter
        c=Counter()
        for v in a: c[int(v//0.25)]+=1
        print("  histogram (0.25 SOL buckets):")
        for b in sorted(c):
            lo=b*0.25; print(f"    {lo:5.2f}-{lo+0.25:5.2f} SOL: {'#'*c[b]} {c[b]}")
        inband=sum(1 for v in a if 1.5<=v<1.75)
        print(f"  in 1.5-1.75 SOL: {inband} ({100*inband/len(a):.0f}%)")
        inbroad=sum(1 for v in a if 1.5<=v<=1.75)
        print(f"  fraction >=1.5 SOL: {sum(1 for v in a if v>=1.5)/len(a)*100:.0f}% ; <1.0 SOL: {sum(1 for v in a if v<1.0)/len(a)*100:.0f}%")

    report(vals,"ALL")
    report(clean,"CLEANED 0<x<50")
    print(f"\ndropped (non-pos or >=50 SOL): {len(dropped)} -> {['%.3f'%d for d in dropped]}", file=sys.stderr)
    print("FAILS:", fails, file=sys.stderr)

if __name__=="__main__":
    main()
