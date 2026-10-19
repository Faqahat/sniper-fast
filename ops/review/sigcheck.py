# REVIEW: verify the Ed25519 signature inside every dumped (presigned) buy tx against the payer key (RFC 8032 verify, pure python)
import sys, json, base64, hashlib
sys.path.insert(0, "/root/indep")
from common import b58dec
p = 2**255 - 19; L = 2**252 + 27742317777372353535851937790883648493
d = -121665 * pow(121666, p - 2, p) % p; I = pow(2, (p - 1) // 4, p)
def xrecover(y):
    xx = (y * y - 1) * pow(d * y * y + 1, p - 2, p); x = pow(xx, (p + 3) // 8, p)
    if (x * x - xx) % p: x = x * I % p
    return x
def add(P, Q):
    x1, y1, z1, t1 = P; x2, y2, z2, t2 = Q
    A = (y1 - x1) * (y2 - x2) % p; B = (y1 + x1) * (y2 + x2) % p; C = t1 * 2 * d * t2 % p; D = z1 * 2 * z2 % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % p, G * H % p, F * G % p, E * H % p)
def mul(s, P):
    Q = (0, 1, 1, 0)
    while s:
        if s & 1: Q = add(Q, P)
        P = add(P, P); s >>= 1
    return Q
def dec(b):
    y = int.from_bytes(b, "little") & ((1 << 255) - 1); x = xrecover(y)
    if (x & 1) != (b[31] >> 7): x = p - x
    return (x, y, 1, x * y % p)
def eq(P, Q): return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0
By = 4 * pow(5, p - 2, p) % p; Bx = xrecover(By); Bx = p - Bx if Bx & 1 else Bx; B = (Bx, By, 1, Bx * By % p)
A_b = b58dec("FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"); A = dec(A_b)
ok = bad = 0; sigs = set()
for l in open(sys.argv[1]):
    r = json.loads(l); raw = base64.b64decode(r["raw"]); sig = raw[1:65]; msg = raw[65:]
    R = sig[:32]; S = int.from_bytes(sig[32:], "little")
    k = int.from_bytes(hashlib.sha512(R + A_b + msg).digest(), "little") % L
    good = S < L and eq(mul(S, B), add(dec(R), mul(k, A)))
    ok += good; bad += not good; sigs.add(R)
print(f"signatures valid: {ok}, INVALID: {bad}; distinct nonces R: {len(sigs)} of {ok + bad} (a repeated R would leak the key)")
