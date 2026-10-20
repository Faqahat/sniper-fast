import json, urllib.request, os, time, re, sys, base64

TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB="ComputeBudget111111111111111111111111111111"
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TRADE_DISC=bytes([189,219,127,211,78,230,97,238])
VSOL0=30_000_000_000
VTOK0=1_073_000_000_000_000  # 1.073e15

# tip account sets
JITO={"3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
"Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
"ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49"}
HELIUS={"4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE","D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ",
"9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta","5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn",
"2nyhqdwKcJZR2vcqCyrYsaPVdAnFoJjiksCXJ7hfEYgD","2q5pghRs6arqVjRvT5gfgWfWcHWmw1ZuCzphgd5KfWGJ",
"wyvPkWjVZz1M8fHQnMMCDTQDbkManefNNhweYk5WkcF","3KCKozbAaF75qEU33jtzozcJ29yJuaLJTy2jFdzUY8bT",
"4vieeGHPYPG2MmyPRcYjdiDmmhN3ww7hsFNap8pVN3Ey","4TQLFNWK8AovT1gFvda5jfw2oJeRMKEmw7aH6MGBJ3or"}
BLOXROUTE={"HWEoBxYs7ssKuudEjzjmpfJVX7Dvi7wescFsVx2L5yoY","3UQUKjhMKaY2S6bjcQD6yHB7utcZt5bfarRCmctpRtUd",
"FjmZZrFvhnqqb9ThCuMVnENaM3JGVuGWNyCAxRJcFpg9","HzYfeM7NnaHiZQPz7YkdbCHkwJqfjBbHZSQHDbqxVpa5"}
# pump protocol accounts we should NOT count as tips (fee recipients etc.)
PUMP_SYS={"CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM","FWsW1xNtWscwNmKv6wVsU1iTzRN6wmmk3MjxRP5tT7hz",
"62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV","9rPYyANsfQZw3DnDmKE3YCQF5E8oDG5eddWk3SPC3LR"}
SYSPROG={"11111111111111111111111111111111"}

def rpc(m,p,tries=6):
    data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for i in range(tries):
        try:
            req=urllib.request.Request(RPC,data=data,headers={"content-type":"application/json"})
            r=json.load(urllib.request.urlopen(req,timeout=90))
            if "error" in r:
                return None
            return r.get("result")
        except Exception:
            time.sleep(0.4*(i+1))
    return None

def b58dec(s):
    n=0
    for c in s: n=n*58+B58.index(c)
    if n==0: return b"\x00"
    return n.to_bytes((n.bit_length()+7)//8,"big")

def parse_trade(b):
    o=8
    o+=32  # mint
    sol=int.from_bytes(b[o:o+8],"little");o+=8
    tok=int.from_bytes(b[o:o+8],"little");o+=8
    isbuy=b[o];o+=1
    o+=32  # user
    o+=8   # ts
    vsol=int.from_bytes(b[o:o+8],"little");o+=8
    vtok=int.from_bytes(b[o:o+8],"little");o+=8
    return dict(sol=sol,tok=tok,isbuy=isbuy,vsol=vsol,vtok=vtok)

def buy_event(tx):
    for l in tx["meta"].get("logMessages") or []:
        if l.startswith("Program data: "):
            try:
                raw=base64.b64decode(l[len("Program data: "):]+"===")
            except Exception:
                continue
            if len(raw)>=8+32+8+8+1+32+8+8+8 and raw[:8]==TRADE_DISC:
                e=parse_trade(raw)
                if e["isbuy"]==1 and 0<e["tok"]<10**18 and e["sol"]>0 and e["vsol"]>VSOL0//2:
                    return e
    return None

def compute_budget(tx):
    cu_price=None; cu_limit=None
    for ix in tx["transaction"]["message"]["instructions"]:
        pid=ix.get("programId") or ("" )
        if pid==CB and ix.get("data"):
            try:
                raw=b58dec(ix["data"])
            except Exception:
                continue
            if not raw: continue
            tag=raw[0]
            if tag==2 and len(raw)>=5:
                cu_limit=int.from_bytes(raw[1:5],"little")
            elif tag==3 and len(raw)>=9:
                cu_price=int.from_bytes(raw[1:9],"little")
    return cu_price,cu_limit

def tips(tx,fee_payer):
    out=[]
    for ix in tx["transaction"]["message"]["instructions"]:
        if ix.get("program")=="system":
            pr=ix.get("parsed") or {}
            if pr.get("type")=="transfer":
                info=pr.get("info",{})
                dst=info.get("destination"); lam=int(info.get("lamports",0))
                src=info.get("source")
                if dst and src==fee_payer and dst not in PUMP_SYS and lam>0:
                    lab="other"
                    if dst in JITO: lab="jito"
                    elif dst in HELIUS: lab="helius"
                    elif dst in BLOXROUTE: lab="bloxroute"
                    elif dst.startswith("noz") or dst.startswith("TEMPa"): lab="nozomi"
                    elif dst.startswith("astra"): lab="astralane"
                    elif dst.startswith("0sl") or dst.startswith("Eb2") or dst.startswith("4Hiw") or dst.startswith("6fQa"): lab="0slot"
                    out.append((dst,lam,lab))
    return out

_block_cache={}
def getblock(slot):
    if slot in _block_cache: return _block_cache[slot]
    b=rpc("getBlock",[slot,{"transactionDetails":"full","rewards":False,"maxSupportedTransactionVersion":1,"encoding":"jsonParsed"}])
    if len(_block_cache)>12: _block_cache.clear()
    _block_cache[slot]=b
    return b

def keys_of(tx):
    return [k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]

def process(mint,cslot,devlog):
    rows=[]
    for sd in (0,1):
        slot=cslot+sd
        blk=getblock(slot)
        if not blk: continue
        for pos,tx in enumerate(blk["transactions"]):
            if not tx.get("meta") or tx["meta"].get("err"): continue
            keys=keys_of(tx)
            if mint not in keys or PUMP not in keys: continue
            logs=tx["meta"].get("logMessages") or []
            if not any(("Instruction: Buy" in l) for l in logs): continue
            e=buy_event(tx)
            if not e: continue
            fp=keys[0]
            cu_price,cu_limit=compute_budget(tx)
            tp=tips(tx,fp)
            nsig=len(tx["transaction"]["signatures"])
            rows.append(dict(mint=mint,slot=slot,sd=sd,pos=pos,fee_payer=fp,
                sol_in=e["sol"],tok_out=e["tok"],vsol=e["vsol"],vtok=e["vtok"],
                cu_price=cu_price,cu_limit=cu_limit,nsig=nsig,
                tip_lam=sum(t[1] for t in tp),tip_labels=",".join(sorted(set(t[2] for t in tp))) if tp else "",
                tip_dests=",".join(t[0] for t in tp)))
    if not rows: return []
    rows.sort(key=lambda r:(r["slot"],r["pos"]))
    # floor from first buy pre-reserves
    f=rows[0]
    pre_vsol=f["vsol"]-f["sol_in"]; dev=max(0,pre_vsol-VSOL0)
    floor_px=(VSOL0+dev)**2/(VSOL0*VTOK0)
    sol_ahead=0
    for i,r in enumerate(rows):
        eff=r["sol_in"]/r["tok_out"]
        r["eff_price"]=eff
        r["floor_px"]=floor_px
        r["fill_mult"]=eff/floor_px
        r["dev_lam"]=dev
        r["dev_log"]=devlog
        r["buy_rank"]=i
        r["is_first"]=(i==0)
        r["sol_ahead"]=sol_ahead
        r["n_ahead"]=i
        r["prio_fee_lam"]=(r["cu_price"]*r["cu_limit"]/1e6) if (r["cu_price"] and r["cu_limit"]) else None
        sol_ahead+=r["sol_in"]
    return rows

def main():
    txt=""
    for fn in ["/root/sniper-fast/paper_blacklist.log","/root/sniper-fast/paper_urihost.log"]:
        try: txt+=open(fn).read()
        except Exception: pass
    seen={}
    for m in re.finditer(r"slot=(\d+) mint=([A-Za-z0-9]+) dev_buy=(\d+)",txt):
        slot=int(m.group(1)); mint=m.group(2); dev=int(m.group(3))
        seen.setdefault((slot,mint),dev)
    launches=sorted(seen.items())
    print(f"launches={len(launches)}",flush=True)
    out=open("/root/fill/rows.jsonl","w")
    nl=0; nr=0
    for (slot,mint),dev in launches:
        try:
            rows=process(mint,slot,dev)
        except Exception as ex:
            print("ERR",mint,repr(ex),flush=True); continue
        nl+=1
        for r in rows:
            out.write(json.dumps(r)+"\n"); nr+=1
        out.flush()
        if nl%10==0: print(f"done {nl}/{len(launches)} rows={nr}",flush=True)
    out.close()
    print(f"FINISHED launches={nl} rows={nr}",flush=True)

if __name__=="__main__":
    main()
