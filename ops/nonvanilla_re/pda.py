import hashlib, sys
sys.path.insert(0,"/root/nonvanilla_re")
from ed import on_curve
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,"big");pad=len(s)-len(s.lstrip("1"));return b"\x00"*pad+full
def b58e(b):
    n=int.from_bytes(b,"big");s=""
    while n>0:n,r=divmod(n,58);s=_A[r]+s
    return "1"*(len(b)-len(b.lstrip(b"\x00")))+s
PDA_MARKER=b"ProgramDerivedAddress"
def find_pda(seeds, prog):
    pb=b58d(prog)
    for bump in range(255,-1,-1):
        h=hashlib.sha256(b"".join(seeds)+bytes([bump])+pb+PDA_MARKER).digest()
        if not on_curve(h):
            return b58e(h),bump
    return None,None
def ata(owner, mint, token_prog):
    ATA="ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
    a,_=find_pda([b58d(owner),b58d(token_prog),b58d(mint)], ATA)
    return a
