# 20-minute discovery: every WINNING (successful) transaction of the big arbitrage wallets -> venue pools + profit
import sys, json, time, collections, concurrent.futures as cf
sys.path.insert(0,'..'); from rpc import rpc
exec(open("../an.py").read().split("txs=json.load")[0])   # b58d
WALLETS=("""MriyaNN8TMp6qRWjfr723PK7xgQK7yCt7Kg2v2PQu7X AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51 rLsi2DPwRLovHzLV5XYxa8B597bv8w8nX7fZHJJf8uy
En3NPq8o9Cynf1Q3eP69AqZmPKmBaDugYnE832o2YuzP GgGap6tiUKhD8XeUZaHpVB3rerb3zKWNouWQJHozDujt R32xAccFis3YzBzGwZ1C4QkGiehLxSao7gDmErA3kjk
GxDC9e7SP9mzhDo4re5HbpLa2RW7gB9DtmThx4i4pXSq 4XBqViD1XYF1qHrErrsXBzDrCapvP9fEFX4LPjXZi9YU 4B8srvotmWddTZuMt4RrBQrnx1sQj2Z7FaXgLbWvpVdd
6AGp6zbGNuyZpmzeswv9KCNU15Rf37UQDqDqFAeHmS8d 9EwQoN74Hzw747EM7wB3WtvgAdRGH1czaPtbqZj1qDj4 DtvmxrTACskMG2W8a6KXgSemUfvyNVeQTgfpJoGvMVKx
HuTshmtwcQkWBLzgW3m4uwcmik7Lmz4YFpYcTqMJpXiP 8L2y55D11k63CAftvW7uMM2mBhtMxLoLnivG9uY2bt8j 4BQ6ATUt26GFdiYQfht23iwfKyYD9D7XbL5ATqNGk3xK
GLiCiNEnku3pQsmkVkRvnDLbfUN9BWbsrPDWLdPaADng """+"AhdtDQrMdDiaNvyLHhJNmhjeNcZQZB8ye7KMbK6QcyFg BLLguHigr3TwY92MNK2G5s6QBK9K5GUSzfCUL8o3YQ4b CzYQ2kFnBxsNEt9Zy34vQ3n5fSDhvA4o4XaTnq1rLvyr Dy1jE82CCKsSE6aRFVfxQZemHqJ1Qa81CvGdLhxnJXJj ARARAw1AL4kKnuwFyU534yoGv5ytexxeVpbcuEvpqi89 DeFG8i8zoJ3hN155nmvLq266ZVxWmNgRaTz5KQVHfe2S DULT2qC5mH15gxTKbrFgxEVHrNeKbkAkNYoq4gU5knL8 Dnq77xMNwqPTj8NRhXvD827HNJNgQvZpqob3oMFus7tE FHpcNSe6tb2n15bAdq4BkeYWGyZKFD7yLYrH92ng7wCT AXmnRBrNtYYyyo82cLBBhnWJ7o1iqNLZbuEVpDB3V666 DcQNaByvstRZCERvb9UJHgHiQe8YX2FMdPptM86psQyz 3KvsoNxgn64nsuHKPBHQJsguef3DgEkP2izE49k6CSAZ 4jjEXcFPXw7WVGXSTb227HW6wfLprjh2RtiHty4GbetE 327677XqTEwYxo8kaQxAJUWvUvzpVoSjiMXMc8u4wQS6 5xXj9RtRo2K2NXu5JL8rMCcg6VhqiV1VX4PuwWJiPWdK DsCJ5siuJTPQtQa3A9N69azGZaWtUPzi9VPp2G9Jfpx9 FUJKrQhxWYu4z59G6JGVfZstjQKi1fY1BZNwoekgs9vL shakRDxyKwaBbduqZTZt8Q4etTALbDLnAANStv9TLH3 8ApoG8cA6mQZyWAs2f86ycLuQzgojgnKRNU9U2eJ742M CQwT1byuHgjKnL6vzmuNaAywKfDBVxDmFVgsQDBWxcWt moodt1QXNtbmiheUJr9EGfch7h5mTxcWqCLyzXxWNu6 Aet81p95mmuKjmMZPqDPmnupgU6RmQT3MmM4JojBEcst 9uGsPcu2a2hJ8XE7U1iqsof54GVTDBjMRoksLRGvTEzQ GDjPqCeSN2f2dq2UjyRuFGamB3haFeqDA7YSfW2tkftd 4vAqkstzmguHUHPCXBfsR1TYbdfdzbEom4tQiGpqgZbM Cn6CDLumBPssj1GkJ7SzdCnnJ4TWxUrNiVx8VbCqoMjX 2EZsc3KXSRusWxWnzEd7efQFcaxYpoh5LkwtvWohNKZB 77777nPhGvFUVAj6uq8MGyLneBt4SMwCScYZDzzztdsa FireuLYd4yjJBhXQyBs3Mq6ZpNEjyHPNPG2eqhTP9RHV GMp5tRPtc9kEJTf7if2uSXiyYH28iqLyKChFqJB8Dgk7 29eV5LuZwwVaoufKr5ShBejYVP6N4JZ14U3M5rffXsjp NALUnJA2AJUYa6xJL1HsorEeFgxxDsfUgYBCX8Pp2zD FtFtF8iamFC3gCv5VYUTBd1G4r1XEc1TbcHyuy6hkJPQ 3zNWpeRBZY7c5eS5fYboheQP5juPqD525qixxbjiVhEQ").split()
WSOL="So11111111111111111111111111111111111111112"
V={"LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo":("DLMM",0),"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA":("PumpSwap",0),
   "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG":("DAMMv2",1),"CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C":("RayCPMM",3),
   "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK":("RayCLMM",2),"675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8":("RayAMMv4",1),
   "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc":("Whirlpool",None)}
def keys(t):
    m=t["transaction"]["message"]; k=list(m["accountKeys"]); la=t["meta"].get("loadedAddresses") or {}
    return k+la.get("writable",[])+la.get("readonly",[])
END=time.time()+15*60
seen={w:set() for w in WALLETS}; first=True
out=open("wins2.jsonl","a")
def fetch(ws):
    w,sig=ws
    try: t=rpc("getTransaction",[sig,{"encoding":"json","maxSupportedTransactionVersion":1}])
    except Exception: return None
    if not t: return None
    k=keys(t); meta=t["meta"]; pools=[]
    ixs=[(ix,True) for ix in t["transaction"]["message"]["instructions"]]+[(ix,False) for g in meta.get("innerInstructions") or [] for ix in g["instructions"]]
    for ix,_ in ixs:
        p=k[ix["programIdIndex"]]
        if p in V:
            name,idx=V[p]; acc=[k[a] for a in ix["accounts"]]
            if idx is None: idx=4 if b58d(ix["data"])[:8].hex()=="2b04ed0b1ac91e62" else 2
            if idx<len(acc): pools.append((name,acc[idx]))
    pre=sum(int(b["uiTokenAmount"]["amount"]) for b in meta["preTokenBalances"] if b.get("owner")==w and b["mint"]==WSOL)
    post=sum(int(b["uiTokenAmount"]["amount"]) for b in meta["postTokenBalances"] if b.get("owner")==w and b["mint"]==WSOL)
    wi=k.index(w) if w in k else 0
    gain=post-pre+meta["postBalances"][wi]-meta["preBalances"][wi]
    return {"w":w,"sig":sig,"slot":t["slot"],"bt":t["blockTime"],"pools":pools,"gain":gain}
with cf.ThreadPoolExecutor(4) as ex:
    while time.time()<END:
        todo=[]
        for w in WALLETS:
            try: r=rpc("getSignaturesForAddress",[w,{"limit":100}])
            except Exception: continue
            new=[x for x in r if x["signature"] not in seen[w]]
            for x in new: seen[w].add(x["signature"])
            if not first: todo+=[(w,x["signature"]) for x in new if x["err"] is None]
        first=False
        for rec in ex.map(fetch,todo):
            if rec: out.write(json.dumps(rec)+"\n"); out.flush()
        print(time.strftime("%H:%M:%S"),"wins fetched",len(todo),flush=True)
        time.sleep(15)
print("done",flush=True)
