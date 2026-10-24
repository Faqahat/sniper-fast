# Minimal base58 (Bitcoin alphabet) encoder/decoder - independent implementation.
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
IDX = {c: i for i, c in enumerate(ALPH)}


def b58enc(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = []
    while n:
        n, r = divmod(n, 58)
        out.append(ALPH[r])
    pad = len(b) - len(b.lstrip(b"\0"))
    return "1" * pad + "".join(reversed(out))


def b58dec(s: str) -> bytes:
    n = 0
    for c in s:
        n = n * 58 + IDX[c]
    pad = len(s) - len(s.lstrip("1"))
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * pad + body
