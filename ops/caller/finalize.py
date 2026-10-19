import json
coh=json.load(open("/root/caller/cohort.json"))
leads=json.load(open("/root/caller/leads.json"))
ctrl2=json.load(open("/root/caller/control2.json"))
rand=ctrl2["cohort_random_activity"]
TP=coh["target_present"]  # 402

genesis={ # first_tx unix times from fund2.py
"4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3":1791842553,
"CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J":1791842359,
"GjsVMaLbPv4ZPL5Yvypzms8iyubXgP16JreJB3FGyGfd":1791842359,
"AMDEmVocLtN5ji2gBY7BrmSHEyM5vt6TGszBbg4crMXg":1791842365,
"G8gTguf7EUwqfwdRhiZ3KCBEgPURVB7LXoDzHif4p6oh":1791842367,
"dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK":1791842458,
"BXB7FF4m5x74ZoUvVHfPJnVBbqWHpMEU1WNUZAL9W8PL":1791842501,
"GTfHPpyyoC6X4uxmhLBWzovQCsSMZ8cfckPt8dcxeKcq":1791842523,
"8ptvshQRZPRaRQBSCRxhHwbJFr6ktyUQ1SATDCLijkBW":1791842523,
"G9sQPg9Eimkwe72w1xH1tPUc9RFNuK6Ufw5AyWy6j7ob":1791842537,
}
ndistinct=ctrl2["ndistinct_mints"]
# enrich cohort rows
for c in coh["cohort"]:
    w=c["wallet"]
    r=rand.get(w,0)
    his_rate=c["co_with_target"]/TP
    base_rate=r/ndistinct if ndistinct else 0
    c["random_mints_bought"]=r
    c["his_pick_rate"]=round(his_rate,4)
    c["base_rate_random"]=round(base_rate,5)
    c["lift"]= round(his_rate/base_rate,1) if base_rate>0 else None  # None=infinite (0 random)
    c["genesis_unix"]=genesis.get(w)
json.dump(coh,open("/root/caller/cohort.json","w"),indent=1)

# print lift table
print("wallet | #his(coW) | his_rate | rand_mints | lift | genesis")
for c in coh["cohort"][:12]:
    print(f"{c['wallet'][:8]}.. | {c['co_with_target']} | {c['his_pick_rate']:.3f} | {c['random_mints_bought']} | {c['lift']} | {c.get('genesis_unix')}")
