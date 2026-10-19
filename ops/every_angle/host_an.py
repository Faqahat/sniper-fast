import json, sys
from collections import Counter
sys.path.insert(0,'/root/profit_backtest')
import common as C
CV2="d6904cec5f8b31b4"; CV1="181ec828051c0777"
# universe hosts from cached create txs (reuse sampled sigs)
us=json.load(open('/root/every_angle/uni_social.json'))
creates={c['mint']:c for c in json.load(open('/root/profit_backtest/creates.json'))}
def uri_of(tx):
    try:
        for ix in tx['transaction']['message']['instructions']:
            if ix.get('programId')!=C.PUMP_B58: continue
            dd=C.b58dec(ix.get('data',''))
            if dd[:8].hex() not in (CV1,CV2): continue
            p=8
            def rs():
                nonlocal p
                ln=int.from_bytes(dd[p:p+4],'little'); p+=4; s=dd[p:p+ln].decode('utf-8','replace'); p+=ln; return s
            rs(); rs(); return rs()
    except: return None
uh=Counter()
for m in us:
    c=creates.get(m)
    if not c: continue
    tx=C.gettx(c['sig'])
    if not tx: continue
    u=uri_of(tx)
    if u and '://' in u: uh[u.split('/')[2]]+=1
tot=sum(uh.values())
print(f"UNIVERSE uri-host dist (n={tot}):")
for h,n in uh.most_common(8): print(f"  {n/tot:.2f}  {h}")
# his hosts
his=json.load(open('/root/every_angle/uris.json'))
hh=Counter(u.split('/')[2] for u in his.values() if '://' in u)
th=sum(hh.values())
print(f"\nHIS uri-host dist (n={th}):")
for h,n in hh.most_common(8): print(f"  {n/th:.2f}  {h}")
