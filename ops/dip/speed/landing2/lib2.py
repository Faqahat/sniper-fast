#!/usr/bin/env python3
# Shared helpers for the HOW_PROS_LAND study: tip map, leader map (slot -> leader -> client / Jito front / location),
# the block clock (INFERRED ms), and loading of reactions.json.gz.
import json, gzip, collections
D = "/home/moiz/sniper-data/landing2"
# ---------- tip map: engine registry + sourced catalogue (fetched 2026-10-03/04) + live doc checks 2026-10-25 ----------
NORM = {"temporal_nozomi": "nozomi", "helius_sender": "helius", "astralane_iris": "astralane", "bloxroute_trader_api": "bloxroute",
        "bloxroute_legacy": "bloxroute", "falcon_corvus": "falcon", "hellomoon_lunar_lander": "lunar", "raiden_bolt": "bolt",
        "everstake_swqos": "everstake", "jupiter_tx": "jupitertx", "quicknode_fastlane": "quicknode_fastlane", "zeroslot": "0slot",
        "nodeone": "node1", "svs_lightspeed_legacy": "svs_lightspeed", "allenhark_relay": "allenhark", "solami_beam": "solami",
        "rpcfast_beam": "rpcfast", "quicknode_fastlane?": "quicknode_fastlane", "p2p_syncro_sender": "p2p_syncro", "quicknode_lil_jit": "quicknode_liljit"}
def norm(s): return NORM.get(s, s)
TIPS = {}
for a, s in json.load(open("/home/moiz/sniper-data/work/tipmap.json")).items(): TIPS[a] = norm(s)
for a, s in json.load(open("/home/moiz/sniper/ops/dip/speed/night/tipmap.json")).items(): TIPS.setdefault(a, norm(s))
_cat = json.load(open("/home/moiz/sniper/data/sender-tip-accounts.json"))
for svc, v in _cat.items():
    if isinstance(v, dict):
        for a in v.get("tip_accounts") or []: TIPS.setdefault(a, norm(svc))
# BlockRazor live list 2026-10-25 (docs.blockrazor.io .../priority-fee-and-tip) adds 5 accounts
for a in ["8EpzWhsr7uyZkfVD7MTHoWqupM14xngzMeUcCkWbY1UG", "56XRik27PddNnR7JkHKqd5pWdMHeqje7TCm1gsdmvnTP", "2DJNtR1tT7vfub7sDJ6v9NGmrzGVFUer5FvjhEcWEpvv",
          "3AveZTS3PJo5qKEqHJci5bjW8neufriirr9mJXfsv4iH", "9DC798ezxU2f2i8ggQ4vsqrsNxdDWJWAFg4cT1xLDR1X"]: TIPS.setdefault(a, "blockrazor")
def svc_of(a): return TIPS.get(a) or ("nozomi" if a.startswith("noz") else None)
# ---------- leaders ----------
_LS = None
def leaders():
    global _LS
    if _LS is None:
        L = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/dip/speed/night/leaders_by_slot.json")).items()}
        for k, v in json.load(open(f"{D}/leaders_prev_epoch.json")).items(): L.setdefault(int(k), v)
        _LS = L
    return _LS
_NODES = {n["pubkey"]: n for n in json.load(open(f"{D}/cluster_nodes_1025.json"))}
_INFO = json.load(open("/home/moiz/sniper/ops/dip/speed/night/leader_info.json"))["client"]
_BF = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json"))["leaders"]
_BA = json.load(open("/home/moiz/sniper/ops/region/leader_rtt_ams.json"))["leaders"]
_GEO = {r["pk"]: r for r in json.load(open("/home/moiz/sniper-data/leader_geo.json"))["rows"]}
def client_raw(pk):
    n = _NODES.get(pk) or {}
    return n.get("clientId") or _INFO.get(pk) or (_BF.get(pk) or {}).get("client") or "?"
def client(pk):
    c = client_raw(pk)
    if c == "JitoLabs": return "Jito-relayer" if jito_front(pk) == "relayer" else "Jito-own"
    return {"AgaveBam": "BAM", "FireBAM": "BAM", "HarmonicAgave": "Harmonic", "HarmonicFiredancer": "Harmonic", "Firedancer": "Firedancer",
            "Frankendancer": "Firedancer", "Rakurai": "Rakurai", "Agave": "Agave"}.get(c, "other")
def client_fine(pk):
    c = client_raw(pk)
    if c == "JitoLabs": return "Jito-relayer" if jito_front(pk) == "relayer" else "Jito-own"
    return c
def jito_front(pk):
    n = _NODES.get(pk) or {}
    tq = n.get("tpuQuic") or ""; g = (n.get("gossip") or "").rsplit(":", 1)[0]
    if not tq: return "?"
    ip, port = tq.rsplit(":", 1)
    return "relayer" if (port == "11228" or ip != g) else "own"
def loc(pk):
    f = (_BF.get(pk) or {}).get("rtt"); a = (_BA.get(pk) or {}).get("rtt"); g = _GEO.get(pk) or {}
    cc = g.get("cc")
    if f is not None and f <= 2.0: return "FRA"
    if a is not None and a <= 2.0: return "AMS"
    if f is not None and a is not None and min(f, a) <= 15: return "EU-other"
    if cc in ("US", "CA"): return "N-America"
    if cc in ("JP", "SG", "KR", "HK", "TW", "IN", "AU", "CN", "TH", "VN", "ID", "MY"): return "Asia"
    if cc: return "other" if (f is None or f > 15) else "EU-other"
    if f is not None: return "EU-other" if min(f, a or 999) <= 30 else "far"
    return "?"
def rtt(pk): return (_BF.get(pk) or {}).get("rtt"), (_BA.get(pk) or {}).get("rtt")
def city(pk): return (_GEO.get(pk) or {}).get("city") or "?"
# ---------- block clock (INFERRED): Alpenglow window = 4 blocks; block 1 records <= 144 ms, blocks 2-4 200 ms each ----------
START = [0.0, 144.0, 344.0, 544.0]; DUR = [144.0, 200.0, 200.0, 200.0]
def tms(s, i, n):
    k = s % 4
    return (s // 4) * 800.0 + START[k] + min(1.0, i / max(n, i + 1)) * DUR[k]
def load():
    with gzip.open(f"{D}/reactions.json.gz", "rt") as f: R = json.load(f)
    R["blk"] = {int(k): v for k, v in R["blk"].items()}
    return R
def nblk(R, s): b = R["blk"].get(s); return (b[0] + 1) if b else None
# ---------- tip-like recipients found in the pros' txs (round amounts, many txs), not in any public list (2026-10-25) ----------
UNK = {"Node1HiScWKC9UmmWYu3AftMdtCZ3qE1qs2FqSLukX8": "unk-Node1", "Node1j2ru8UmagMVkpcRW8xB6PmrvKEbFoZPSvo1fex": "unk-Node1",
       "D1Mc6j9xQWgR1o1Z7yU5nVVXFQiAYx7FG9AW1aVfwrUM": "unk-D1Mc", "MANKAZYMJSUFEui63ZzSRzk6NsdZj8ej7wkcrk13vzS": "unk-MANKAZ",
       "Sp4JHSh9cksfzXbgK7Pq2ovtn8LirLQydaJKTsiNT77": "unk-Sp", "SpWrza9E63MQuHeGnnfzmtLVCs3pBdjyKPXUABPo9nq": "unk-Sp",
       "SpagSJmnh8E9cGT5Y431xPPaS2c1xLREGGCWN9yDeUf": "unk-Sp", "Sp1xMS2cbw83SZDNr4AGqkBYYLjb3LvVnmDSrTMaHkr": "unk-Sp",
       "Sp1x2AqpQckPLaWnWCJUNg8k6qQexfaEWcSRKf5JcDV": "unk-Sp", "FASTYKWXRfAoty7SQCM1mGVrmPUyyNcF4tc3DUkLDAu9": "unk-FAST",
       "APeX2oLtjYehgTMUCA971L8htM7tGNqsXHDz5NrivhhX": "unk-APeX", "AS6RWKUikRdNwicsZoDtT1iYGfk1XZo6aH5fCJxVDfCA": "unk-AS6R",
       "AVwZ5MvvukUhHX5LJtpeKKpqqRtdA5XaN1WZLApZySJF": "unk-AVwZ"}
def route(tips, sdp):
    s = {svc_of(a) or "?" + a[:6] for a, _ in tips}
    s |= {UNK[a] for a, v in sdp if a in UNK}
    return "+".join(sorted(s)) or "none"
