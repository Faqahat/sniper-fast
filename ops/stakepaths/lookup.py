#!/usr/bin/env python3
# READ-ONLY helper: joins getVoteAccounts + on-chain validator-info names.
# usage: lookup.py --total | <pubkey or name-regex> ...
import json, sys, re

d = json.load(open("/root/stakepaths/voteaccounts.json"))["result"]
allv = d["current"] + d["delinquent"]
tot = sum(v["activatedStake"] for v in allv)
allv.sort(key=lambda v: -v["activatedStake"])
rank = {v["nodePubkey"]: i + 1 for i, v in enumerate(allv)}
info = {}
for a in json.load(open("/root/stakepaths/validatorinfo.json"))["result"]:
    i = a["account"]["data"]["parsed"]["info"]
    node = i["keys"][1]["pubkey"]
    info[node] = i["configData"]
bynode = {v["nodePubkey"]: v for v in allv}
byvote = {v["votePubkey"]: v for v in allv}


def show(v, tag=""):
    n = v["nodePubkey"]
    cd = info.get(n, {})
    s = v["activatedStake"] / 1e9
    print(f"{tag}#{rank[n]:>4} {s:>12,.0f} SOL {100*v['activatedStake']/tot:6.3f}% "
          f"node={n} vote={v['votePubkey']} comm={v['commission']} "
          f"name={cd.get('name','')!r} web={cd.get('website','')!r}")


if len(sys.argv) > 1 and sys.argv[1] == "--total":
    print(f"total activated stake {tot/1e9:,.0f} SOL; validators {len(allv)}")
    sys.exit()
for q in sys.argv[1:]:
    if q in bynode:
        show(bynode[q], "[node] ")
    elif q in byvote:
        show(byvote[q], "[vote] ")
    else:
        hit = False
        for n, cd in info.items():
            txt = " ".join(str(x) for x in cd.values())
            if re.search(q, txt, re.I):
                hit = True
                if n in bynode:
                    show(bynode[n], f"[{q}] ")
                else:
                    print(f"[{q}] (no vote acct) node={n} name={cd.get('name','')!r} web={cd.get('website','')!r}")
        if not hit:
            print(f"[{q}] not found")
