import sys, re
# Join broad collector's launch (dev,vanilla) + done (pnl) lines by mint -> A/B several filters on the SAME tokens.
LOG="/root/sniper-fast/paper_broad.log"
dev={}; van={}
for ln in open(LOG):
    m=re.search(r"PAPER launch #\d+ slot=\d+ mint=([1-9A-HJ-NP-Za-km-z]+) dev_buy=(\d+) vanilla=(\w+)",ln)
    if m: dev[m.group(1)]=int(m.group(2))/1e9; van[m.group(1)]=(m.group(3)=="true")
rows=[]
for ln in open(LOG):
    m=re.search(r"PAPER done mint=([1-9A-HJ-NP-Za-km-z]+) .* @1\.00=([-+0-9.]+)",ln)
    if m and m.group(1) in dev:
        rows.append((m.group(1), dev[m.group(1)], van.get(m.group(1),True), float(m.group(2))))
def stat(sel,tag):
    v=sorted(r[3] for r in rows if sel(r) and r[3]<=18)  # drop r-cap outliers
    n=len(v)
    if not n: print(f"  {tag:28} n=0"); return
    print(f"  {tag:28} n={n:4} mean={sum(v)/n:+.4f} median={v[n//2]:+.4f} win={100*sum(1 for x in v if x>0)/n:3.0f}% net={sum(v):+.2f}")
print(f"=== A/B over {len(rows)} closed trades (broad collector, his exit ladder) ===")
stat(lambda r:True,                         "ALL (broad, no filter)")
stat(lambda r:r[1]>=0.5,                    "dev>=0.5")
stat(lambda r:r[1]>=0.5 and r[2],           "dev>=0.5 + vanilla  <<our filter")
stat(lambda r:r[1]>=1.0,                    "dev>=1.0")
stat(lambda r:r[1]>=1.0 and r[2],           "dev>=1.0 + vanilla")
stat(lambda r:0.5<=r[1]<=8,                 "dev 0.5-8")
stat(lambda r:r[1]>=0.5 and not r[2],       "dev>=0.5 NON-vanilla only")
stat(lambda r:r[1]<0.5,                     "dev<0.5 (the dead class)")
