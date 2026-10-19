import os, sys, json, time, base64, urllib.request, hashlib, requests

RPC = os.environ["RPC_URL"]
CREATOR = "bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

_ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58decode(s):
    n=0
    for c in s: n=n*58+_ALPH.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,'big') if n else b''
    pad=len(s)-len(s.lstrip('1'))
    return b'\0'*pad+full
def b58encode(b):
    n=int.from_bytes(b,'big'); out=''
    while n: n,r=divmod(n,58); out=_ALPH[r]+out
    pad=len(b)-len(b.lstrip(b'\0'))
    return '1'*pad+out

sess=requests.Session()
def rpc(method, params, tries=7):
    body={"jsonrpc":"2.0","id":1,"method":method,"params":params}
    for i in range(tries):
        try:
            r=sess.post(RPC, json=body, timeout=60)
            if r.status_code==429:
                time.sleep(2*(i+1)); continue
            d=r.json()
            if "error" in d:
                time.sleep(1.2*(i+1)); continue
            return d.get("result")
        except Exception:
            time.sleep(1.2*(i+1))
    return None

# ed25519 on-curve
q = 2**255 - 19
def inv(x): return pow(x, q-2, q)
d = (-121665 * inv(121666)) % q
I = pow(2, (q-1)//4, q)
def xrecover(y):
    xx=(y*y-1)*inv(d*y*y+1)
    x=pow(xx,(q+3)//8,q)
    if (x*x-xx)%q!=0: x=(x*I)%q
    if x%2!=0: x=q-x
    return x
def is_on_curve(s):
    y=int.from_bytes(s,'little') & ((1<<255)-1)
    sign=(s[31]>>7)&1
    try: x=xrecover(y)
    except Exception: return False
    if x&1!=sign: x=q-x
    return (-x*x+y*y-1-d*x*x*y*y)%q==0

PUMPB=b58decode(PUMP)
def bonding_curve(mint):
    seeds=[b"bonding-curve", b58decode(mint)]
    for bump in range(255,-1,-1):
        h=hashlib.sha256(b''.join(seeds)+bytes([bump])+PUMPB+b"ProgramDerivedAddress").digest()
        if not is_on_curve(h):
            return b58encode(h)
    return None

if __name__=="__main__" and len(sys.argv)>1 and sys.argv[1]=="selftest":
    for m in ["3Ci5HwoT71pY9GmEtKJEzNEuFFWtfE5FW7X6wKsrbGvG"]:
        bc=bonding_curve(m)
        print("mint",m,"-> curve",bc)
        ai=rpc("getAccountInfo",[bc,{"encoding":"base64","commitment":"confirmed"}])
        print("  owner:", ai["value"]["owner"] if ai and ai.get("value") else None)
