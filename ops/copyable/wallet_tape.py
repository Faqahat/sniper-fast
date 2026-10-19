#!/usr/bin/env python3
"""General per-wallet pump/pumpswap trade tape puller + characterizer.
Uses balance-delta accounting (robust across bonding-curve v2 and pumpswap AMM).
For each wallet: pull recent sigs, parse pump-related txs, extract per-trade
(mint, side, sol, tokens, price, slot, blockTime), pair FIFO per mint ->
realized PnL (SOL), win%, median hold (seconds & slots), entry timing, #trades.
Writes /root/copyable/tapes/<wallet>.json
Usage: python3 wallet_tape.py <wallet1> [wallet2 ...]
"""
import requests, json, sys, time, statistics as st
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

RPC = open('/root/snipe_study50/rpc_url.txt').read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"          # bonding curve
PUMPSWAP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"      # migrated AMM
WSOL = "So11111111111111111111111111111111111111112"
# Broad memecoin DEX / aggregator venue set (balance-delta accounting is venue-agnostic;
# this filter just confirms the tx is a swap, not a transfer/LP/stake).
DEX_PROGS = {
    PUMP, PUMPSWAP,
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",   # Raydium AMM v4
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",   # Raydium CLMM
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",   # Raydium CPMM
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",    # Jupiter v6
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",    # Meteora DLMM
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB",   # Meteora pools
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",    # Orca whirlpool
    "obriQD1zbpyLz95G5n7nJe6a4DPjpFwa5XYPoNm113y",    # Obric
    "5quBtoiQqxF9Jv6KYKctB59NT3gtJD2Y65kdnB1Uev3h",   # (raydium legacy)
}

sess = requests.Session()
def rpc(method, params, tries=5):
    for i in range(tries):
        try:
            r=sess.post(RPC, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=40)
            j=r.json()
            if 'result' in j: return j['result']
            err=j.get('error',{})
            if err.get('code') in (-32019,-32005) or 'rate' in str(err).lower():
                time.sleep(0.8); continue
            return None
        except Exception:
            time.sleep(0.6)
    return None

def get_sigs(addr, limit_total=1600):
    out=[]; before=None
    while len(out)<limit_total:
        p=[addr,{"limit":1000}]
        if before: p[1]["before"]=before
        res=rpc("getSignaturesForAddress",p)
        if not res: break
        out.extend(res)
        if len(res)<1000: break
        before=res[-1]['signature']
    return out[:limit_total]

def get_tx(sig):
    return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed"}])

def program_ids(tx):
    """set of program ids invoked (top + inner)"""
    meta=tx.get('meta') or {}
    msg=tx['transaction']['message']
    pids=set()
    for ix in msg.get('instructions',[]):
        if ix.get('programId'): pids.add(ix['programId'])
    for inner in meta.get('innerInstructions',[]):
        for ix in inner.get('instructions',[]):
            if ix.get('programId'): pids.add(ix['programId'])
    return pids

def parse_trade(tx, wallet):
    """Return (mint, side, sol_amt, tok_amt, price) or None using balance deltas.
    side='buy' tokens increase; 'sell' tokens decrease."""
    meta=tx.get('meta') or {}
    if meta.get('err') is not None: return None
    pids=program_ids(tx)
    if not (pids & DEX_PROGS): return None
    # token balance change for wallet, per mint. Track WSOL separately (it is SOL flow).
    pre={}; post={}; pre_wsol=0.0; post_wsol=0.0
    for b in meta.get('preTokenBalances',[]) or []:
        if b.get('owner')==wallet:
            amt=float(b['uiTokenAmount'].get('uiAmount') or 0)
            if b.get('mint')==WSOL: pre_wsol+=amt
            else: pre[b['mint']]=amt
    for b in meta.get('postTokenBalances',[]) or []:
        if b.get('owner')==wallet:
            amt=float(b['uiTokenAmount'].get('uiAmount') or 0)
            if b.get('mint')==WSOL: post_wsol+=amt
            else: post[b['mint']]=amt
    mints=set(pre)|set(post)
    best=None
    for m in mints:
        d=post.get(m,0)-pre.get(m,0)
        if abs(d)>0 and (best is None or abs(d)>abs(best[1])):
            best=(m,d)
    if not best: return None
    mint, tok_delta = best
    # SOL flow = native lamport delta (+fee addback if fee payer) + WSOL balance delta
    msg=tx['transaction']['message']
    keys=[k['pubkey'] if isinstance(k,dict) else k for k in msg.get('accountKeys',[])]
    try: widx=keys.index(wallet)
    except ValueError: widx=0
    preB=meta.get('preBalances',[]); postB=meta.get('postBalances',[])
    if widx>=len(preB): return None
    lam_delta=(postB[widx]-preB[widx])
    fee=meta.get('fee',0) or 0
    if widx==0: lam_delta += fee
    sol_delta=lam_delta/1e9 + (post_wsol-pre_wsol)   # neg on buy (spent), pos on sell (recv)
    if tok_delta>0:  # buy
        sol=-sol_delta  # spent (positive)
        side='buy'
    else:
        sol=sol_delta   # received (positive if sold)
        side='sell'
    tok=abs(tok_delta)
    if tok<=0 or sol<=0: return None
    price=sol/tok
    return (mint, side, sol, tok, price)

def process_wallet(wallet, max_sigs=1600, max_tx=1400):
    sigs=get_sigs(wallet, max_sigs)
    succ=[s for s in sigs if s.get('err') is None]
    bt=[s['blockTime'] for s in sigs if s.get('blockTime')]
    span=[min(bt),max(bt)] if bt else None
    trades=[]
    def work(s):
        tx=get_tx(s['signature'])
        if not tx: return None
        tr=parse_trade(tx, wallet)
        if not tr: return None
        mint,side,sol,tok,price=tr
        return {"sig":s['signature'],"slot":tx['slot'],"bt":tx.get('blockTime'),
                "mint":mint,"side":side,"sol":sol,"tok":tok,"price":price}
    cnt=0
    with ThreadPoolExecutor(max_workers=20) as ex:
        for r in ex.map(work, succ[:max_tx]):
            cnt+=1
            if r: trades.append(r)
    trades.sort(key=lambda t:(t['slot'], t['sig']))
    return {"wallet":wallet,"n_sigs":len(sigs),"n_succ":len(succ),"n_err":len(sigs)-len(succ),
            "span":span,"trades":trades}

def pair_fifo(trades):
    """FIFO pair buys/sells per mint -> round trips. Returns list of positions."""
    by_mint=defaultdict(list)
    for t in trades: by_mint[t['mint']].append(t)
    positions=[]
    for mint, ts in by_mint.items():
        ts.sort(key=lambda x:(x['slot'],))
        # running inventory of buy lots (tok, sol, slot, bt)
        lots=[]
        realized_sol_in=0.0; realized_sol_out=0.0
        buy_tok=0.0; buy_sol=0.0; sell_tok=0.0; sell_sol=0.0
        first_buy=None; last_sell=None
        holds=[]  # per matched token-weighted hold
        for t in ts:
            if t['side']=='buy':
                lots.append([t['tok'],t['sol'],t['slot'],t['bt']])
                buy_tok+=t['tok']; buy_sol+=t['sol']
                if first_buy is None: first_buy=t
            else:
                sell_tok+=t['tok']; sell_sol+=t['sol']
                last_sell=t
                rem=t['tok']
                # match against lots FIFO for hold
                while rem>1e-9 and lots:
                    lot=lots[0]
                    take=min(rem, lot[0])
                    if t['bt'] and lot[3]:
                        holds.append((t['bt']-lot[3], take))
                    lot[0]-=take; rem-=take
                    if lot[0]<=1e-9: lots.pop(0)
        # realized PnL (SOL): sell proceeds - cost basis of sold tokens.
        # approximate cost basis by avg buy price * sold tok (bounded by tok sold)
        avg_buy_px = (buy_sol/buy_tok) if buy_tok>0 else 0
        matched_tok=min(sell_tok, buy_tok)
        cost_basis=avg_buy_px*matched_tok
        proceeds=sell_sol*(matched_tok/sell_tok) if sell_tok>0 else 0
        pnl=proceeds-cost_basis
        # token-weighted median hold seconds
        hold_s=None
        if holds:
            tot=sum(w for _,w in holds)
            flat=[]
            for h,w in holds: flat.append(h)  # simple median of hold durations
            hold_s=st.median(flat)
        r_mult = (proceeds/cost_basis) if cost_basis>0 else None
        positions.append({"mint":mint,"buy_tok":buy_tok,"buy_sol":buy_sol,
                          "sell_tok":sell_tok,"sell_sol":sell_sol,
                          "avg_buy_px":avg_buy_px,"pnl_sol":pnl,"r_mult":r_mult,
                          "n_buys":sum(1 for x in ts if x['side']=='buy'),
                          "n_sells":sum(1 for x in ts if x['side']=='sell'),
                          "first_buy_slot":first_buy['slot'] if first_buy else None,
                          "first_buy_bt":first_buy['bt'] if first_buy else None,
                          "last_sell_bt":last_sell['bt'] if last_sell else None,
                          "hold_s":hold_s,"fully_closed": sell_tok>=buy_tok*0.9})
    return positions

def summarize(wallet, trades, positions):
    closed=[p for p in positions if p['sell_tok']>0 and p['buy_sol']>0]
    pnls=[p['pnl_sol'] for p in closed]
    rmults=[p['r_mult'] for p in closed if p['r_mult'] is not None]
    holds=[p['hold_s'] for p in closed if p['hold_s'] is not None]
    wins=sum(1 for p in pnls if p>0)
    tot_pnl=sum(pnls)
    n_buys=sum(1 for t in trades if t['side']=='buy')
    n_sells=sum(1 for t in trades if t['side']=='sell')
    # trades/day
    span=None
    bts=[t['bt'] for t in trades if t['bt']]
    tpd=None
    if bts and len(bts)>1:
        days=(max(bts)-min(bts))/86400
        tpd=(n_buys/days) if days>0 else None
    return {"wallet":wallet,"n_trades":len(trades),"n_buys":n_buys,"n_sells":n_sells,
            "n_positions":len(positions),"n_closed":len(closed),
            "tot_realized_pnl_sol":tot_pnl,
            "win_rate": (wins/len(pnls)) if pnls else None,
            "mean_r": (sum(rmults)/len(rmults)) if rmults else None,
            "median_r": st.median(rmults) if rmults else None,
            "median_hold_s": st.median(holds) if holds else None,
            "p25_hold_s": (sorted(holds)[len(holds)//4] if holds else None),
            "p75_hold_s": (sorted(holds)[len(holds)*3//4] if holds else None),
            "trades_per_day": tpd,
            "span_bt":[min(bts),max(bts)] if bts else None}

if __name__=='__main__':
    wallets=sys.argv[1:]
    import os
    os.makedirs('/root/copyable/tapes',exist_ok=True)
    summaries=[]
    for w in wallets:
        print(f"[{w}] pulling...",file=sys.stderr)
        try:
            data=process_wallet(w)
        except Exception as e:
            print(f"  ERR {e}",file=sys.stderr); continue
        positions=pair_fifo(data['trades'])
        summ=summarize(w, data['trades'], positions)
        summ['n_sigs']=data['n_sigs']; summ['n_succ']=data['n_succ']
        json.dump({"summary":summ,"positions":positions,"trades":data['trades'],
                   "span":data['span'],"n_sigs":data['n_sigs'],"n_succ":data['n_succ']},
                  open(f'/root/copyable/tapes/{w}.json','w'))
        summaries.append(summ)
        print(f"  trades={summ['n_trades']} closed={summ['n_closed']} "
              f"pnl={summ['tot_realized_pnl_sol']:.3f}SOL win={summ['win_rate']} "
              f"medHold={summ['median_hold_s']}s medR={summ['median_r']} tpd={summ['trades_per_day']}",
              file=sys.stderr)
    json.dump(summaries, open('/root/copyable/tape_summaries.json','w'),indent=1)
    print("wrote tape_summaries.json",file=sys.stderr)
