# Step 1: tape + create + shape extraction for run_20261104_1240 chunks NOT already in /home/moiz/sniper-vulture2x/tape
# (frozen extract.py / crefix.py / bin_shape.one logic, outputs redirected to /home/moiz/sniper-data/vulture_probe_score).
import sys,glob,os,gzip,json,pickle
sys.dont_write_bytecode=True
sys.path.insert(0,"/home/moiz/sniper-omen6")
import extract as X, crefix as CF
D="/home/moiz/sniper-data/vulture_probe_score"
X.OUT=D+"/tape"; CF.OUT=D+"/cre"
RUN="run_20261104_1240"
have={os.path.basename(f)[:-4] for f in glob.glob(f"/home/moiz/sniper-vulture2x/tape/{RUN}/*.pkl")}
g=[f for f in sorted(glob.glob(f"/home/moiz/sniper-data/collect/{RUN}/txs/*.jsonl.gz")) if os.path.basename(f)[:-9] not in have]
PUMP='6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
SKIP={'ComputeBudget111111111111111111111111111111','11111111111111111111111111111111','ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL','TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb','pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ',PUMP}
def shape(f):   # copy of bin_shape.one, output to D/shape
    o=f"{D}/shape/{f.split('/')[-3]}_{os.path.basename(f)[:-9]}.pkl"
    if os.path.exists(o): return
    out={}
    try:
        for line in gzip.open(f,'rt',errors='replace'):
            if '"Sell"' not in line or PUMP not in line: continue
            try: d=json.loads(line)
            except Exception: continue
            if d.get('err') is not None: continue
            pr=d.get('progs') or []
            out[(d['s'],d.get('i') or 0)]=(d.get('fee',0),d.get('cup',0),d.get('cul',0),sum(t[1] if isinstance(t,list) and len(t)>1 else 0 for t in d.get('tips') or []),
                 len([p for p in pr if p not in SKIP]), int(PUMP in pr), len(d.get('signers') or []), len(d.get('ixn') or []))
    except EOFError: pass
    pickle.dump(out,open(o,'wb'))
if __name__=='__main__':
    from multiprocessing import Pool
    print('chunks to do',len(g),g[0],g[-1],flush=True)
    with Pool(6) as p:
        p.map(X.one,g,chunksize=1); p.map(CF.one,g,chunksize=2); p.map(shape,g[-8:],chunksize=1)
    print('done',len(g),flush=True)
