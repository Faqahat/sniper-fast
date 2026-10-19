#!/usr/bin/env python3
import json, re
from collections import Counter
H=[json.loads(l) for l in open('/root/meta400/his_meta.jsonl')]
P=[json.loads(l) for l in open('/root/meta400/pop_meta.jsonl')]
NH,NP=len(H),len(P)

def host(u):
    if not u: return None
    m=re.match(r'https?://([^/]+)',u); return m.group(1) if m else None

FEATS=[
 ("TOKEN-2022 program", lambda r: r.get('mint_program')=='TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'),
 ("decimals==6", lambda r: r.get('decimals')==6),
 ("mint_authority renounced(null)", lambda r: r.get('mint_authority') is None and r.get('mint_program')),
 ("freeze_authority none(null)", lambda r: r.get('freeze_authority') is None and r.get('mint_program')),
 ("update_authority null", lambda r: r.get('update_authority') is None and 'tokenMetadata' in (r.get('extensions') or [])),
 ("has metadataPointer+tokenMetadata ext", lambda r: tuple(r.get('extensions') or ())==('metadataPointer','tokenMetadata')),
 ("suffix 'pump'", lambda r: r.get('suffix')=='pump'),
 ("createdOn ~ pump.fun", lambda r: (r.get('uri_createdOn') or '').replace('https://','').replace('http://','').strip('/').startswith('pump')),
 ("has twitter", lambda r: bool(r.get('uri_twitter'))),
 ("twitter on x.com/twitter.com", lambda r: host(r.get('uri_twitter')) in ('x.com','twitter.com') if r.get('uri_twitter') else False),
 ("has telegram", lambda r: bool(r.get('uri_telegram'))),
 ("has website", lambda r: bool(r.get('uri_website'))),
 ("has discord", lambda r: bool(r.get('uri_discord'))),
 ("has ANY social", lambda r: bool(r.get('uri_twitter') or r.get('uri_telegram') or r.get('uri_website') or r.get('uri_discord'))),
 ("has image", lambda r: bool(r.get('uri_image'))),
 ("has description", lambda r: bool(r.get('uri_description') not in (None,''))),
 ("showName present", lambda r: r.get('uri_showName') in (True,'true')),
 ("has coin_community key", lambda r: 'coin_community' in (r.get('uri_keys') or [])),
 ("uri_fetch_ok", lambda r: str(r.get('uri_fetch_status','')).startswith('ok')),
 ("dev_buy>=0.5 SOL", lambda r: (r.get('dev_buy') or 0)>=0.5),
 ("dev_buy>=1.0 SOL", lambda r: (r.get('dev_buy') or 0)>=1.0),
 ("dev_buy>=0.3 SOL", lambda r: (r.get('dev_buy') or 0)>=0.3),
]
def pct(recs,fn):
    return 100*sum(1 for r in recs if fn(r))/len(recs)

rows=[]
for name,fn in FEATS:
    h=pct(H,fn); p=pct(P,fn)
    rows.append((name,h,p,h-p))

print(f"{'ATTRIBUTE':40s} {'his%':>7s} {'pop%':>7s} {'diff':>7s}")
print("-"*66)
for name,h,p,d in rows:
    flag=''
    if h>=95 and p>=95: flag='  <- invariant & UNIVERSAL (not distinguishing)'
    elif h>=95 and (h-p)>=20: flag='  <- INVARIANT & DISTINGUISHING *'
    elif (h-p)>=25: flag='  <- distinguishing but NOT invariant'
    print(f"{name:40s} {h:6.1f}% {p:6.1f}% {d:+6.1f}%{flag}")

# near-invariant list for his (>=95)
print("\n== His near-invariant (>=98%) attributes ==")
for name,h,p,d in rows:
    if h>=98: print(f"  {name}: his {h:.1f}% / pop {p:.1f}%")
