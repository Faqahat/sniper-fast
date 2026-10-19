#!/usr/bin/env python3
"""Long-horizon trajectory + graduation harvester.
For each unbiased create_v2 mint (reuse creates.json), paginate bonding-curve trades from
create forward, build full price path out to WINDOW slots, and detect migration/graduation.
Resumable: one JSON per mint in OUTDIR. Reuses profit_backtest/common.py RPC + disk cache."""
import sys, os, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, "/root/profit_backtest")
import common as C

CREATES = "/root/profit_backtest/creates.json"
OUTDIR  = "/root/edge_hunt/long_traj"
os.makedirs(OUTDIR, exist_ok=True)
WINDOW   = int(os.environ.get("WINDOW", "5000"))     # slots after create to track (~33 min @2.5/s)
TXCAP    = int(os.environ.get("TXCAP", "400"))       # max txs to fetch per mint for the path
MAXPAGES = int(os.environ.get("MAXPAGES", "30"))     # sig-list pages per mint
WORKERS  = int(os.environ.get("WORKERS", "16"))
LIMIT    = int(os.environ.get("LIMIT", "0"))         # 0=all

# graduation: pump bonding curve completes at ~85 SOL real reserves; migration withdraws it.
MIGRATE_WITHDRAW_SOL = 60.0   # a single tx pulling >60 SOL off the curve = migrate/withdraw

def harvest_one(m):
    mint = m["mint"]; create_slot = m["create_slot"]
    outf = os.path.join(OUTDIR, mint + ".json")
    if os.path.exists(outf):
        try:
            r = json.load(open(outf))
            if r.get("_v") == 3: return ("skip", mint)
        except Exception: pass
    bc = C.bonding_curve_of(mint)
    # 1) paginate sig list from newest back until we pass create_slot (whole life, bounded by WINDOW end)
    hi = create_slot + WINDOW
    allsigs = []; before=None; pages=0
    while pages < MAXPAGES:
        pr=[bc, {"limit":1000}]
        if before: pr[1]["before"]=before
        ch = C.rpc("getSignaturesForAddress", pr)
        if not ch: break
        allsigs += ch; before = ch[-1]["signature"]; pages+=1
        if len(ch) < 1000: break
        if ch[-1]["slot"] <= create_slot: break
    total_curve_txs = sum(1 for s in allsigs if not s["err"])
    # window = [create, create+WINDOW], oldest->newest, non-error
    sigs = [s for s in allsigs if not s["err"] and create_slot <= s["slot"] <= hi]
    sigs.sort(key=lambda s:(s["slot"], s["signature"]))
    # 2) fetch txs (capped, but keep chronological coverage: if too many, stride-sample)
    use = sigs
    strided = False
    if len(sigs) > TXCAP:
        step = len(sigs)/TXCAP
        use = [sigs[int(i*step)] for i in range(TXCAP)]
        strided = True
    series=[]; cum_sol=0.0; migrated_slot=None; migrate_bt=None; cosnipers0=0; peak_curve_sol=0.0
    for s in use:
        tx = C.gettx(s["signature"])
        if not tx or not tx.get("meta"): continue
        meta=tx["meta"]; keys=C._keys(tx)
        def tok(owner):
            pre=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("preTokenBalances",[]) if t.get("owner")==owner)
            post=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("postTokenBalances",[]) if t.get("owner")==owner)
            return post-pre
        dtok=tok(bc); dsol=0.0; curve_post=None
        if bc in keys:
            idx=keys.index(bc); dsol=(meta["postBalances"][idx]-meta["preBalances"][idx])/1e9
            curve_post=meta["postBalances"][idx]/1e9
        if dtok>0 and dsol>0:
            continue  # the create tx row
        # migration/withdraw detection: huge SOL leaving the curve
        if dsol < -MIGRATE_WITHDRAW_SOL and migrated_slot is None:
            migrated_slot = s["slot"]; migrate_bt = tx.get("blockTime")
        if curve_post is not None and curve_post>peak_curve_sol: peak_curve_sol=curve_post
        if abs(dtok)>0 and abs(dsol)>1e-9:
            px=abs(dsol)/abs(dtok)
            series.append((s["slot"], tx.get("blockTime"), px, round(dsol,6)))
            if s["slot"]==create_slot and dsol>0: cosnipers0+=1
    out = {"_v":3, "mint":mint, "create_slot":create_slot, "blockTime":m.get("blockTime"),
           "entry_px":m.get("entry_px"), "dev_buy":m.get("dev_buy"),
           "creator":m.get("creator"), "creator_fee_bps":m.get("creator_fee_bps"),
           "mayhem":m.get("mayhem"), "holder_reward":m.get("holder_reward"), "cashback":m.get("cashback"),
           "total_curve_txs":total_curve_txs, "n_window":len(sigs), "strided":strided,
           "cosnipers0":max(0,cosnipers0-1), "peak_curve_sol":round(peak_curve_sol,3),
           "migrated_slot":migrated_slot, "migrate_bt":migrate_bt,
           "series":series}
    json.dump(out, open(outf,"w"))
    return ("ok", mint)

def main():
    creates = json.load(open(CREATES))
    if LIMIT: creates = creates[:LIMIT]
    print(f"harvesting {len(creates)} mints, WINDOW={WINDOW} TXCAP={TXCAP}", flush=True)
    ok=skip=0; t0=time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs=[ex.submit(harvest_one,m) for m in creates]
        done=0
        for fu in as_completed(futs):
            try: st,_=fu.result()
            except Exception as e: st="err"
            done+=1
            if st=="ok": ok+=1
            elif st=="skip": skip+=1
            if done%100==0:
                print(f"  {done}/{len(creates)} ok={ok} skip={skip} elapsed={time.time()-t0:.0f}s", flush=True)
    print(f"DONE ok={ok} skip={skip} total={len(creates)} in {time.time()-t0:.0f}s", flush=True)

if __name__=="__main__": main()
