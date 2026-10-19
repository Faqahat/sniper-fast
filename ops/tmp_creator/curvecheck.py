import sys, json, base64
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, bonding_curve, b58encode, b58decode, CREATOR
import struct
seeds=["3Ci5HwoT71pY9GmEtKJEzNEuFFWtfE5FW7X6wKsrbGvG","9bzW2gMmA193QuNsxn6xuUiuPPe7sPXFy5oTFS8wV5xG","Cw9e9ZceFpVvEucufJyvX3YpC9gyyHnPBspha6hEmiiG","2mczEAedUhHRP5GQ43gP2qTVWCij9NgfidmNJpya4YKU"]
print("creator =", CREATOR)
for m in seeds:
    bc=bonding_curve(m)
    ai=rpc("getAccountInfo",[bc,{"encoding":"base64","commitment":"confirmed"}])
    v=ai.get("value") if ai else None
    if not v:
        print(m[:8],"-> NO CURVE ACCOUNT (migrated/graduated?)"); continue
    raw=base64.b64decode(v["data"][0]); owner=v["owner"]
    vt,vs,rt,rs,ts=struct.unpack_from("<QQQQQ",raw,8)
    complete=raw[48]
    creator=b58encode(raw[49:81]) if len(raw)>=81 else "N/A"
    print(f"{m[:8]} len={len(raw)} owner={owner[:6]} complete={complete} real_sol={rs/1e9:.2f} vsol={vs/1e9:.2f} creator={creator} match={creator==CREATOR}")
