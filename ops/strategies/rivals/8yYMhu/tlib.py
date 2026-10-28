"""market-tape access for 8yYMhu (mtape.npy sorted by mint/slot/idx/j, from the haqqml fresh tape; ids -> names via mints/users.json)"""
import json, functools
import numpy as np
D = "/home/moiz/sniper-data/rivals/8yYMhu"; TP = "/home/moiz/sniper-data/haqqml/fresh/tape"
@functools.lru_cache(None)
def tape():
    M = np.load(f"{D}/mtape.npy", mmap_mode="r"); sp = np.load(f"{D}/mspan.npz")
    return M, sp["m"], sp["a"], sp["b"]
@functools.lru_cache(None)
def names():
    return json.load(open(f"{TP}/mints.json")), json.load(open(f"{TP}/users.json"))
@functools.lru_cache(None)
def mid():
    return {m: i for i, m in enumerate(names()[0])}
@functools.lru_cache(None)
def uid():
    return {u: i for i, u in enumerate(names()[1])}
def trades_k(k):
    M, m, a, b = tape(); p = np.searchsorted(m, k)
    if p >= len(m) or m[p] != k: return None
    return np.asarray(M[a[p]:b[p]])
def trades(mint):
    k = mid().get(mint)
    return None if k is None else trades_k(k)
