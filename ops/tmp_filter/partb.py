import sys; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,acct,parse_curve,PUMP,b58enc,rpc
import json
MINT="HNwcHVQeV9MqbR9KhEWZK62Mfv48awKh4RCtxmMbpump"
WAL="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
# get earliest signatures for the mint: page back to oldest
all_sigs=[]; before=None
while True:
    batch=sigs(MINT,1000,before=before)
    if not batch: break
    all_sigs+=batch
    if len(batch)<1000: break
    before=batch[-1]["signature"]
    if len(all_sigs)>6000: break
print("total sigs on mint:",len(all_sigs))
oldest=all_sigs[-1]; newest=all_sigs[0]
print("oldest slot",oldest["slot"],"newest slot",newest["slot"],"span slots",newest["slot"]-oldest["slot"])
print("blockTime span (s):", (newest.get("blockTime") or 0)-(oldest.get("blockTime") or 0))
# parse create tx (oldest)
ct=tx(oldest["signature"])
create_slot=oldest["slot"]
# find pump instruction + SOL moved by signer (dev buy)
def analyze_tx(t):
    if not t: return None
    msg=t["transaction"]["message"]; meta=t["meta"]
    signer=msg["accountKeys"][0]["pubkey"]
    # sol delta of signer
    keys=[k["pubkey"] for k in msg["accountKeys"]]
    pre=meta["preBalances"]; post=meta["postBalances"]
    sd={keys[i]:(post[i]-pre[i])/1e9 for i in range(len(keys))}
    logs=meta.get("logMessages",[])
    return signer,sd.get(signer),logs,keys
sg,devsol,logs,keys=analyze_tx(ct)
print("CREATE signer(creator):",sg)
print("creator SOL delta in create tx:",round(devsol,4) if devsol else devsol)
print("pump-related logs (first 12):")
for l in logs:
    if any(x in l for x in ["Instruction:","mayhem","Mayhem","fee","Fee","reward","Reward","vanilla","buy","Buy","Create","create"]):
        print("   ",l[:120])
# curve state now
cv=parse_curve_addr=None
# derive bonding curve PDA? easier: scan create tx accounts for the curve (owned by pump). Try each writable acct
print()
print("=== Checking 4yFAz involvement ===")
hit=[s for s in all_sigs if False]
# cross-check: did WAL sign any tx? pull WAL sigs until? too big. Instead check each mint tx signer quickly for first 40 txs
buyers=set()
for s in all_sigs[-60:][::-1][:40]:
    t=tx(s["signature"])
    if not t: continue
    try: buyers.add(t["transaction"]["message"]["accountKeys"][0]["pubkey"])
    except: pass
print("WAL among first-40-tx signers:", WAL in buyers)
print("sample early signers:",list(buyers)[:6])
