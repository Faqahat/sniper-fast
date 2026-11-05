# shapes (sell tx shape features) for every run_20261104_1240 chunk not yet in vulture2x/shape or our shape folder
import sys,glob,os; sys.dont_write_bytecode=True
sys.argv=[sys.argv[0]]
import s1_tape as S
have={os.path.basename(f) for f in glob.glob('/home/moiz/sniper-vulture2x/shape/*.pkl')+glob.glob(S.D+'/shape/*.pkl')}
g=[f for f in S.g if f"run_20261104_1240_{os.path.basename(f)[:-9]}.pkl" not in have]
g+= [f for f in sorted(glob.glob('/home/moiz/sniper-data/collect/run_20261104_1240/txs/*.jsonl.gz')) if f"run_20261104_1240_{os.path.basename(f)[:-9]}.pkl" not in have and f not in g]
from multiprocessing import Pool
print('shape chunks',len(g),flush=True)
with Pool(6) as p: p.map(S.shape,g,chunksize=1)
print('done',flush=True)
