import requests, json, sys, time, hashlib
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PFEE="pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtE4gUjSGAfvkx"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
WSOL="So11111111111111111111111111111111111111112"
BUYDISC="e1f7501ed5b38488"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,"big");pad=len(s)-len(s.lstrip("1"));return b"\x00"*pad+full
def b58e(b):
    n=int.from_bytes(b,"big");s=""
    while n>0:n,r=divmod(n,58);s=_A[r]+s
    return "1"*(len(b)-len(b.lstrip(b"\x00")))+s
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if "result" in j: return j["result"]
            time.sleep(0.5)
        except Exception as e: time.sleep(0.6)
    return None
def get_tx(sig,ver=0):return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":ver,"encoding":"jsonParsed"}])
def allkeys(tx):
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    keys=[a["pubkey"] for a in msg["accountKeys"]]
    la=meta.get("loadedAddresses") or {}
    keys+=la.get("writable",[])+la.get("readonly",[])
    return keys
def find_buy(tx):
    msg=tx["transaction"]["message"]; keys=allkeys(tx)
    out=[]
    for ix in msg.get("instructions",[]):
        pid=ix.get("programId")
        if pid!=PUMP: continue
        d=ix.get("data")
        if not d: continue
        try: raw=b58d(d)
        except: continue
        if raw[:8].hex()!=BUYDISC: continue
        # account list (jsonParsed gives list of pubkeys in ix["accounts"])
        accs=ix.get("accounts",[])
        out.append((raw,accs))
    return out
def ainfo(pk):
    return rpc("getAccountInfo",[pk,{"encoding":"base64"}])

# PDA derivation
def find_pda(seeds, prog):
    pb=b58d(prog)
    for bump in range(255,-1,-1):
        data=b"".join(seeds)+bytes([bump])+pb+b"ProgramDerivedAddress"
        h=hashlib.sha256(data).digest()
        # check off-curve: ed25519 point check approximated; just return first that is off-curve
        if not on_curve(h):
            return b58e(h),bump
    return None,None
# minimal ed25519 on-curve check
import nacl.bindings if False else None
def on_curve(b):
    # use the pynacl check if available else fallback
    try:
        from nacl.signing import VerifyKey
        try:
            VerifyKey(b); return True
        except Exception: return False
    except Exception:
        return False
