import sys, time, json, base64
sys.path.insert(0, "/root/indep")
from common import rpc, events, MINT_AUTH, b58enc, TRADE_DISC
r=rpc("getSignaturesForAddress",[MINT_AUTH,{"limit":30}])
for x in r[:30]:
    t=rpc("getTransaction",[x["signature"],{"encoding":"json","maxSupportedTransactionVersion":1,"commitment":"confirmed"}])
    for l in t["meta"]["logMessages"]:
        if l.startswith("Program data: "):
            raw=base64.b64decode(l[14:]+"===")
            if raw[:8]==TRADE_DISC:
                o=8; mint=b58enc(raw[o:o+32]); o+=32
                vals=[]
                sol=int.from_bytes(raw[o:o+8],"little"); tok=int.from_bytes(raw[o+8:o+16],"little")
                isb=raw[o+16]; user=b58enc(raw[o+17:o+49]); ts=int.from_bytes(raw[o+49:o+57],"little")
                p=o+57
                q=[int.from_bytes(raw[p+8*i:p+8*i+8],"little") for i in range(4)]
                p2=p+32; fr=b58enc(raw[p2:p2+32]); p2+=32
                fbps,fee=[int.from_bytes(raw[p2+8*i:p2+8*i+8],"little") for i in range(2)]; p2+=16
                cr=b58enc(raw[p2:p2+32]); p2+=32
                cbps,cfee=[int.from_bytes(raw[p2+8*i:p2+8*i+8],"little") for i in range(2)]
                print(len(raw), mint[-6:], "sol",sol,"tok",tok,isb,"ts",ts,"vsol,vtok,rsol,rtok",q,"fee",fbps,fee,"cfee",cbps,cfee, raw[p2+16:].hex()[:80])
