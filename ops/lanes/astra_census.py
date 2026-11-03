#!/usr/bin/env python3
"""Astralane census (READ-ONLY on the recorder chunks): how many pump.fun competitors land through Astralane, measured from
the on-chain tip destinations of their LANDED txs.

Inputs : <collect>/run_*/txs/txs_<unix>.jsonl.gz (5-min gz JSONL: every landed tx touching a tracked pump.fun mint).
Window : the last --hours of chunks by the unix time in the file name, ending at the newest chunk modified >= --min-age s ago
         (a truncated gzip keeps what was read). Daily runs overlap at the rotation (old run's 20-min tail vs the new run's
         first minutes): a tx in both is counted once (the newer run's copy; the old run's copy is skipped by signature).
Tip map: src/send/mod.rs known_tip_accounts() + OTHER_TIP_ACCOUNTS, then data/sender-tip-accounts.json, then ops/rec/tipmap.json.
         RPC Fast Beam accounts (incl. the 2 Rpcfast-kind ones) stay "rpcfast_beam" (Beam may route via Astralane; not counted
         as astralane). A tx's services = recorder 'tips' (positive deltas to tip accounts, from the full delta list) + positive
         deltas in the top-14 'sd' list to any mapped account. Failed txs roll back their tip: counted, never classified.
Race   : dump = pump TradeEvent SELL with sol >= --dump-sol on the bonding curve; racer = successful BUY tx of the same mint by
         another user after the dump in chain order within 1 slot (same slot, higher index; or slot + 1). Our wallets are not
         competitors (counted apart).
Outputs: --out: summary.txt, census.json, wallets.csv, race_top.csv, dumps.csv.gz, users.csv.gz, unknown_dest.csv
Usage  : python3 ops/lanes/astra_census.py --hours 12 [--procs 5] [--out DIR] [--min-age 240] [--collect DIR] [--dump-sol 1]
"""
import argparse, base64, collections, csv, datetime, glob, gzip, hashlib, io, json, os, re, statistics, struct, sys, time, zlib
from array import array
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # /home/moiz/sniper
DISC = bytes.fromhex("bddb7fd34ee661ee")          # pump.fun TradeEvent (as ops/strategies/presend/real/decode.py)
CPI = bytes.fromhex("e445a52e51cb9a1d")           # anchor event-CPI prefix, stripped
B64KEY = "vdt/007mY"                              # base64 of the TradeEvent discriminator: fast line filter
CPI_B64 = base64.b64encode(CPI).decode()[:10]     # "5EWlLlHLmh": an event-CPI-prefixed record
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
HEAD = re.compile(r'\{"s":(\d+),"i":(\d+),"bt":(\d+|null),"sig":"([^"]+)","err":(n?)')
SIGN_RE = re.compile(r'"signers":\[([^\]]*)\]')
PKT = datetime.timezone(datetime.timedelta(hours=5))

NAMED = [("8yYM", "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3"), ("haqq", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"),
         ("HkQ7", "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"), ("DF7e", "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9"),
         ("ssssswdk", "ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E"), ("GKd5", "GKd5EMzRhbprZXZfsbJczo4SrfF99XZWQA82bazaQr14"),
         ("omego", "omegoMAe1AMY5MFKQQr3JwXVy8F4eCvmBAfcpo8XAfq"), ("A2kc", "A2kcamqspcFgpX3BHomww4xGkv6R1hS2m1N41TFBCXhf"),
         ("CZ77", "CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx"), ("6VzX", "6VzXcLk9rCLDHgRBmUGKK8HY2KvhHmR4pZPCxi4tA1kx"),
         ("E2x1", "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"), ("DYXD", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw"),
         ("sssssDdM", "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"), ("ETwE", "ETwEAQPLnAMRbU9EXjXTYoq8msfLkaD8x1AD1Zcbnz6b"),
         ("dKMj", "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK")]
OURS = [("ours_AMS", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"), ("ours_FRA", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")]
LABEL = {k: n for n, k in NAMED + OURS}
OURSET = {k for _, k in OURS}
NONCOMP = {"BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s": "pump_mayhem_agent"}   # program-run Mayhem agent (Mayhem program, never a signer)
ASTRA, BEAM = "astralane", "rpcfast_beam"

# ---------------------------------------------------------------- tip account -> service
KIND_NAME = {"Iris": ASTRA, "Helius": "helius", "JitoBundle": "jito", "JitoTx": "jito", "Nozomi": "nozomi", "ZeroSlot": "0slot",
             "Bolt": "bolt", "Falcon": "falcon", "FalconUdp": "falcon", "Lunar": "lunar", "Glaive": "glaive", "BlockRazor": "blockrazor",
             "Soyas": "soyas", "Solami": "solami", "NextBlock": "nextblock", "FlashBlock": "flashblock", "Bloxroute": "bloxroute",
             "NodeOne": "nodeone", "Everstake": "everstake", "JupiterTx": "jupiter", "Landx": "landx", "SpeedLanding": "speedlanding",
             "Rpcfast": BEAM}
NORM = {"helius_sender": "helius", "temporal_nozomi": "nozomi", "astralane_iris": ASTRA, "bloxroute_trader_api": "bloxroute",
        "bloxroute_legacy": "bloxroute", "falcon_corvus": "falcon", "node1": "nodeone", "hellomoon_lunar_lander": "lunar",
        "raiden_bolt": "bolt", "everstake_swqos": "everstake", "jupiter_tx": "jupiter", "jupitertx": "jupiter",
        "svs_lightspeed_legacy": "svs_lightspeed", "quicknode_lil_jit": "jito", "quicknode_fastlane": "quicknode_fastlane?",
        "solami_beam": "solami", "rpcfast": BEAM, "astralane": ASTRA}
B58RE = r'"([1-9A-HJ-NP-Za-km-z]{32,44})"'

def build_tipmap():
    m, src = {}, {}
    rs = open(os.path.join(ROOT, "src/send/mod.rs")).read()
    body = rs[rs.index("pub fn known_tip_accounts"):]; body = body[:body.index("\n}\n")]
    for kinds, lst in re.findall(r"((?:SendKind::\w+\s*\|?\s*)+)=>\s*&\[(.*?)\]", body, re.S):
        ks = re.findall(r"SendKind::(\w+)", kinds)
        name = next((KIND_NAME[k] for k in ks if k in KIND_NAME), None)
        for a in re.findall(B58RE, lst):
            if name: m.setdefault(a, name); src.setdefault(a, "mod.rs")
    oth = rs[rs.index("pub static OTHER_TIP_ACCOUNTS"):rs.index("pub fn known_tip_accounts")]
    for a, n in re.findall(r'\("([1-9A-HJ-NP-Za-km-z]{32,44})",\s*"([^"]+)"\)', oth):
        m.setdefault(a, NORM.get(n, n)); src.setdefault(a, "mod.rs:OTHER")
    try:
        for k, v in json.load(open(os.path.join(ROOT, "data/sender-tip-accounts.json"))).items():
            for a in (v.get("tip_accounts") or []) if isinstance(v, dict) else []:
                if isinstance(a, str): m.setdefault(a, NORM.get(k, k)); src.setdefault(a, "sender-tip-accounts.json")
    except Exception as e:
        print("WARN sender-tip-accounts.json:", e, file=sys.stderr)
    try:
        for a, n in json.load(open(os.path.join(ROOT, "ops/rec/tipmap.json"))).items():
            m.setdefault(a, NORM.get(n, n)); src.setdefault(a, "tipmap.json")
    except Exception as e:
        print("WARN tipmap.json:", e, file=sys.stderr)
    return m, src

TIPNAME, TIPSRC = build_tipmap()

# ---------------------------------------------------------------- decoding
def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n:
        n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

def sigh(sig): return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")

def trade_events(evl, cache):
    """pump TradeEvents of one tx: [(mint, sol, is_buy, user)] in log order (j = list index)."""
    out = []
    for e in evl or []:
        for ch in e.split(" "):
            if not ch.startswith(B64KEY) and not ch.startswith(CPI_B64):   # anything else is not a TradeEvent
                continue
            try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
            except Exception: continue
            if b[:8] == CPI: b = b[8:]
            if b[:8] != DISC or len(b) < 113: continue
            mb, ub = b[8:40], b[57:89]
            mint = cache.get(mb) or cache.setdefault(mb, b58(mb))
            user = cache.get(ub) or cache.setdefault(ub, b58(ub))
            sol = struct.unpack_from("<Q", b, 40)[0]
            out.append((mint, sol, b[56] == 1, user))
    return out

def services(r, unmapped):
    """{service: lamports} paid by a landed tx: recorder tips (full delta list) + mapped positive deltas in sd (top 14)."""
    out = {}; seen = set()
    for k, d in r.get("tips") or []:
        if d <= 0 or k in seen: continue
        seen.add(k)
        n = TIPNAME.get(k)
        if n is None:
            n = "nozomi(prefix)" if k.startswith("noz") else "rec_unmapped"
            unmapped[k] += 1
        out[n] = out.get(n, 0) + d
    for k, d in r.get("sd") or []:
        if d > 0 and k not in seen and k in TIPNAME:
            seen.add(k); out[TIPNAME[k]] = out.get(TIPNAME[k], 0) + d
    return out

# ---------------------------------------------------------------- per-chunk worker
def scan(task):
    cid, fn, skipbytes, dump_lamports = task
    skip = None
    if skipbytes:
        a = array("Q"); a.frombytes(skipbytes); skip = set(a)
    t0 = time.time()
    T = collections.Counter()                     # totals
    svc_n = collections.Counter(); svc_tip = collections.defaultdict(collections.Counter)
    W = collections.defaultdict(list)            # named/ours wallet -> tx records
    U = {}                                       # identity (payer or event user) -> [n, nbuy, nsell, ntipped, nmulti, {svc: n}]
    FP = collections.Counter()                   # failed txs per fee payer
    unmapped = collections.Counter()
    UN = {}                                      # positive-delta non-signer accounts in successful buys: acct -> [n_notip, n_tipped, [d], [d/sol], payers]
    B = collections.defaultdict(list)            # (mint, slot) -> buy records
    dumps = []
    slots = set(); bmin = bmax = None; smin = smax = None
    cache = {}
    trunc = False
    named_all = LABEL
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if not m:
                    T["bad_lines"] += 1; continue
                sig = m.group(4)
                if skip is not None and sigh(sig) in skip:
                    T["dup_skipped"] += 1; continue
                s = int(m.group(1)); i = int(m.group(2)); bt = int(m.group(3)) if m.group(3) != "null" else None
                T["lines"] += 1; slots.add(s)
                if smin is None or s < smin: smin = s
                if smax is None or s > smax: smax = s
                if bt is not None:
                    if bmin is None or bt < bmin: bmin = bt
                    if bmax is None or bt > bmax: bmax = bt
                ok = m.group(5) == "n"
                if not ok or B64KEY not in line:
                    sm = SIGN_RE.search(line)
                    sg = [x[1:-1] for x in sm.group(1).split(",")] if sm and sm.group(1) else []
                    if not ok:
                        T["failed"] += 1
                        if sg: FP[sg[0]] += 1
                    else:
                        T["succ_nontrade"] += 1
                    for k, w in enumerate(sg):
                        if w in named_all:
                            W[w].append(dict(sig=sig, s=s, i=i, bt=bt, ok=ok, trade=False, match="payer" if k == 0 else "signer"))
                    continue
                r = json.loads(line)
                evs = trade_events(r.get("ev"), cache)
                sg = r.get("signers") or ["?"]; payer = sg[0]
                if not evs:
                    T["succ_nontrade"] += 1
                    for k, w in enumerate(sg):
                        if w in named_all:
                            W[w].append(dict(sig=sig, s=s, i=i, bt=bt, ok=True, trade=False, match="payer" if k == 0 else "signer"))
                    continue
                T["trade_txs"] += 1; T["trade_events"] += len(evs)
                svc = services(r, unmapped)
                cup = r.get("cup"); fee = r.get("fee")
                has_buy = any(e[2] for e in evs); has_sell = any(not e[2] for e in evs)
                T["trade_buy_txs"] += has_buy; T["trade_sell_txs"] += has_sell
                if svc:
                    T["tipped"] += 1
                    if len(svc) > 1: T["multi"] += 1
                    for k, v in svc.items(): svc_n[k] += 1; svc_tip[k][v] += 1
                    if has_buy: T["tipped_buy_txs"] += 1
                else:
                    if has_buy: T["notip_buy_txs"] += 1
                users = {e[3] for e in evs}
                idents = users | {payer}
                for idn in idents:
                    own = [e for e in evs if e[3] == idn] or evs
                    u = U.get(idn)
                    if u is None: u = U[idn] = [0, 0, 0, 0, 0, {}]
                    u[0] += 1; u[1] += any(e[2] for e in own); u[2] += any(not e[2] for e in own)
                    if svc:
                        u[3] += 1; u[4] += len(svc) > 1
                        for k in svc: u[5][k] = u[5].get(k, 0) + 1
                    if idn in named_all:
                        mt = "both" if (idn == payer and idn in users) else ("payer" if idn == payer else "user")
                        W[idn].append(dict(sig=sig, s=s, i=i, bt=bt, ok=True, trade=True, match=mt, buy=any(e[2] for e in own),
                                           sell=any(not e[2] for e in own), svc=svc, cup=cup, fee=fee,
                                           sol=sum(e[1] for e in own), payer=payer))
                svct = tuple(sorted(svc.items()))
                for j, (mint, sol, buy, user) in enumerate(evs):
                    if buy:
                        B[(mint, s)].append((s, i, j, user, payer, sol, sig, svct, cup, bt))
                    elif sol >= dump_lamports:
                        dumps.append((s, i, j, mint, user, payer, sol, sig, bt, svct))
                # unknown-destination screen: positive deltas to non-signer, non-tip accounts in successful buys
                bsol = sum(e[1] for e in evs if e[2])
                if has_buy and bsol > 0:
                    sgs = set(sg)
                    for k, d in r.get("sd") or []:
                        if d <= 0 or k in sgs or k in TIPNAME or k in users: continue
                        x = UN.get(k)
                        if x is None: x = UN[k] = [0, 0, [], [], set()]
                        if svc: x[1] += 1
                        else:
                            x[0] += 1
                            if len(x[2]) < 64: x[2].append(d); x[3].append(d / bsol)
                            if len(x[4]) < 64: x[4].add(payer)
    except (EOFError, OSError, ValueError, zlib.error) as ex:
        trunc = repr(ex)[:100]
    # race candidates: local racers per dump + edge buys (slots whose predecessor or pre-predecessor is missing here)
    edge_slots = {x for x in slots if (x - 1 not in slots) or (x - 2 not in slots)}
    dres = []
    for d in dumps:
        s, i, j, mint, user = d[0], d[1], d[2], d[3], d[4]
        rs = [b for b in B.get((mint, s), ()) if b[1] > i and b[3] != user] + [b for b in B.get((mint, s + 1), ()) if b[3] != user]
        dres.append((d, rs))
    edge = [(k[0], b) for k, lst in B.items() if k[1] in edge_slots for b in lst]
    UNr = {k: [v[0], v[1], v[2], v[3], len(v[4])] for k, v in UN.items() if v[0] >= 3}
    UNr = dict(sorted(UNr.items(), key=lambda kv: -kv[1][0])[:400])
    return dict(cid=cid, fn=fn, T=dict(T), svc_n=dict(svc_n), svc_tip={k: dict(v) for k, v in svc_tip.items()}, W=dict(W), U=U,
                FP=dict(FP), unmapped=dict(unmapped), UN=UNr, dumps=dres, edge=edge, smin=smin, smax=smax, bmin=bmin, bmax=bmax,
                trunc=trunc, nslots=len(slots), nedge=len(edge_slots), secs=round(time.time() - t0, 1))

def sig_hashes(fn):
    out = array("Q"); trunc = False
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if m: out.append(sigh(m.group(4)))
    except (EOFError, OSError, ValueError, zlib.error) as ex:
        trunc = repr(ex)[:100]
    return fn, out.tobytes(), trunc

# ---------------------------------------------------------------- helpers
def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None

def med_counter(c):
    tot = sum(c.values())
    if not tot: return None
    lo_pos, hi_pos = (tot - 1) // 2, tot // 2; acc = 0; lo = hi = None
    for v in sorted(c):
        acc += c[v]
        if lo is None and acc > lo_pos: lo = v
        if acc > hi_pos: hi = v; break
    return (lo + hi) / 2

def utc(t): return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
def pkt(t): return datetime.datetime.fromtimestamp(t, PKT).strftime("%m-%d %H:%M PKT")
def pct(a, b): return (100.0 * a / b) if b else 0.0
def fmt_l(x): return "-" if x is None else f"{int(round(x)):,}"

def svc_shares(recs):
    """recs: iterable of svc tuples/dicts. -> (n, n_tipped, Counter(service -> n txs), n_multi)"""
    n = nt = nm = 0; c = collections.Counter()
    for sv in recs:
        n += 1
        names = [k for k, _ in sv] if isinstance(sv, tuple) else list(sv)
        if names: nt += 1
        if len(names) > 1: nm += 1
        for k in names: c[k] += 1
    return n, nt, c, nm

def mix_str(c, n, top=4):
    return ", ".join(f"{k}{' (Beam, maybe Astralane)' if k == BEAM else ''} {pct(v, n):.0f}%" for k, v in c.most_common(top)) or "-"

def verdict(nt, na):
    if nt == 0: return "never (no tipped tx)"
    sh = na / nt; lown = " (low n)" if nt < 30 else ""
    if sh >= 0.5: return "RELIES on Astralane" + lown
    if sh >= 0.05: return "uses Astralane" + lown
    return ("never" if na == 0 else "never (<5%)") + lown

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=12.0)
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--out", default="/home/moiz/sniper-data/lanes/census")
    ap.add_argument("--collect", default="/home/moiz/sniper-data/collect")
    ap.add_argument("--min-age", type=int, default=240)
    ap.add_argument("--dump-sol", type=float, default=1.0)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    t0 = time.time(); now = time.time()
    os.makedirs(a.out, exist_ok=True)
    dump_lamports = int(a.dump_sol * 1e9)

    # ---- chunks in the window
    runs = {}
    for f in glob.glob(os.path.join(a.collect, "run_*", "txs", "txs_*.jsonl.gz")):
        try: t = int(os.path.basename(f)[4:-9])
        except ValueError: continue
        age = now - os.path.getmtime(f)
        if age < a.min_age: continue
        runs.setdefault(os.path.basename(os.path.dirname(os.path.dirname(f))), []).append((t, f, os.path.getsize(f), age))
    allc = sorted(x for v in runs.values() for x in v)
    if not allc: sys.exit("no chunks")
    t_last = allc[-1][0]; t_end = t_last + 300; t_start = t_end - a.hours * 3600
    sel = {r: sorted(x for x in v if x[0] >= t_start) for r, v in runs.items()}
    sel = {r: v for r, v in sel.items() if v}
    order = sorted(sel, key=lambda r: min(x[0] for x in runs[r]))
    newest = allc[-1]
    partial_newest = (os.path.getmtime(newest[1]) < newest[0] + 300)
    print(f"window {utc(t_start)} .. {utc(t_end)} ({pkt(t_start)} .. {pkt(t_end)}); runs {order}; chunks "
          f"{sum(len(v) for v in sel.values())} ({sum(x[2] for v in sel.values() for x in v) / 1e9:.2f} GB gz)", flush=True)

    # ---- overlap between consecutive runs: skip the older run's copy of txs the newer run also recorded
    skipmap = {}; overlap_info = []
    with Pool(a.procs) as pool:
        for ra, rb in zip(order, order[1:]):
            a_last = sel[ra][-1][0]; b_first = sel[rb][0][0]
            if a_last + 300 <= b_first: continue
            bz = [x[1] for x in sel[rb] if x[0] <= a_last + 900]
            az = [x[1] for x in sel[ra] if x[0] + 300 >= b_first - 900]
            hs = array("Q")
            for fn, by, tr in pool.imap_unordered(sig_hashes, bz):
                h = array("Q"); h.frombytes(by); hs.extend(h)
            hb = hs.tobytes()
            for fn in az: skipmap[fn] = hb
            overlap_info.append(dict(older=ra, newer=rb, newer_chunks=len(bz), older_chunks=len(az), sigs=len(hs)))
            print(f"overlap {ra} -> {rb}: {len(hs)} sigs from {len(bz)} newer chunks, skip in {len(az)} older chunks", flush=True)

        tasks = []
        for r in order:
            for t, fn, size, age in sel[r]:
                tasks.append((len(tasks), fn, skipmap.get(fn), dump_lamports, size))
        tasks.sort(key=lambda x: -x[4])
        tasks = [x[:4] for x in tasks]

        T = collections.Counter(); svc_n = collections.Counter(); svc_tip = collections.defaultdict(collections.Counter)
        W = collections.defaultdict(list); U = {}; FP = collections.Counter(); unmapped = collections.Counter()
        UN = {}; dumps = {}; edge = collections.defaultdict(list); chunks_meta = []
        bmin = bmax = None
        done = 0
        for res in pool.imap_unordered(scan, tasks):
            done += 1
            cid = res["cid"]
            T.update(res["T"]); svc_n.update(res["svc_n"])
            for k, v in res["svc_tip"].items(): svc_tip[k].update(v)
            for w, lst in res["W"].items(): W[w].extend(lst)
            for k, v in res["U"].items():
                u = U.get(k)
                if u is None: U[k] = v; continue
                for z in range(5): u[z] += v[z]
                for s, n in v[5].items(): u[5][s] = u[5].get(s, 0) + n
            FP.update(res["FP"]); unmapped.update(res["unmapped"])
            for k, v in res["UN"].items():
                x = UN.get(k)
                if x is None: UN[k] = [v[0], v[1], list(v[2]), list(v[3]), v[4]]
                else:
                    x[0] += v[0]; x[1] += v[1]; x[4] += v[4]
                    if len(x[2]) < 512: x[2].extend(v[2]); x[3].extend(v[3])
            for d, rs in res["dumps"]:
                key = (d[7], d[2])
                if key not in dumps: dumps[key] = (d, cid, rs)
            for mint, b in res["edge"]: edge[(mint, b[0])].append((cid, b))
            if res["bmin"] is not None:
                bmin = res["bmin"] if bmin is None else min(bmin, res["bmin"]); bmax = res["bmax"] if bmax is None else max(bmax, res["bmax"])
            chunks_meta.append(dict(file=res["fn"], lines=res["T"].get("lines", 0), dup_skipped=res["T"].get("dup_skipped", 0),
                                    slots=res["nslots"], edge_slots=res["nedge"], trunc=res["trunc"], secs=res["secs"]))
            if done % 20 == 0 or res["trunc"]:
                print(f"  {done}/{len(tasks)} chunks, {T['lines']:,} lines, {len(dumps):,} dumps, {time.time() - t0:.0f}s"
                      + (f" TRUNC {os.path.basename(res['fn'])}: {res['trunc']}" if res["trunc"] else ""), flush=True)
    print(f"scan done {time.time() - t0:.0f}s", flush=True)

    # ---------------------------------------------------------------- race
    D = []; ours_first = 0; ours_racer_sigs = set(); agent_first = 0; agent_racer_sigs = set()
    racer_sigs = {}; first_by_user = collections.defaultdict(list); racer_by_user = collections.defaultdict(dict)
    for (sig, j), (d, cid, rs) in dumps.items():
        s, i, mint, user = d[0], d[1], d[3], d[4]
        c = list(rs)
        for (ecid, b) in edge.get((mint, s), ()):
            if ecid != cid and b[1] > i and b[3] != user: c.append(b)
        for (ecid, b) in edge.get((mint, s + 1), ()):
            if ecid != cid and b[3] != user: c.append(b)
        best = {}
        for b in c:
            if b[6] == sig: continue
            k = b[6]
            if k not in best or (b[0], b[1], b[2]) < (best[k][0], best[k][1], best[k][2]): best[k] = b
        rl = sorted(best.values(), key=lambda b: (b[0], b[1], b[2]))
        is_ours = lambda b: b[3] in OURSET or b[4] in OURSET
        is_agent = lambda b: b[3] in NONCOMP or b[4] in NONCOMP
        if rl and is_ours(rl[0]): ours_first += 1
        if rl and is_agent(rl[0]): agent_first += 1
        comp = [b for b in rl if not is_ours(b) and not is_agent(b)]
        for b in rl:
            if is_ours(b): ours_racer_sigs.add(b[6])
            elif is_agent(b): agent_racer_sigs.add(b[6])
        for b in comp:
            racer_sigs[b[6]] = b
            racer_by_user[b[3]][b[6]] = b
        f = comp[0] if comp else None
        if f is not None: first_by_user[f[3]].append((f, s))
        D.append(dict(slot=s, idx=i, j=d[2], bt=d[8], mint=mint, seller=user, seller_payer=d[5], sol=d[6], sig=sig,
                      seller_svc="+".join(k for k, _ in d[9]), n_racers=len(comp), n_same=sum(1 for b in comp if b[0] == s),
                      first_user=f[3] if f else "", first_payer=f[4] if f else "", first_slot=f[0] if f else "",
                      first_idx=f[1] if f else "", first_same=int(f[0] == s) if f else "",
                      first_svc="+".join(f"{k}:{v}" for k, v in f[7]) if f else "", first_cup=f[8] if f else "",
                      first_sol=f[5] if f else "", first_sig=f[6] if f else "", ours_first=int(bool(rl) and is_ours(rl[0]))))
    fr = [rec for lst in first_by_user.values() for rec, s in lst]
    allr = svc_shares(b[7] for b in racer_sigs.values())
    fst = svc_shares(b[7] for b in fr)
    fss = svc_shares(b[7] for b, s in ((rec, s) for lst in first_by_user.values() for rec, s in lst) if b[0] == s)
    fs1 = svc_shares(b[7] for b, s in ((rec, s) for lst in first_by_user.values() for rec, s in lst) if b[0] == s + 1)

    # ---------------------------------------------------------------- named wallets
    wrows = []
    for lab, w in NAMED + OURS:
        recs = {}
        for x in W.get(w, []):
            k = x["sig"]
            if k not in recs or (x.get("trade") and not recs[k].get("trade")): recs[k] = x
        tr = [x for x in recs.values() if x["ok"] and x["trade"]]
        fail = [x for x in recs.values() if not x["ok"]]
        oth = [x for x in recs.values() if x["ok"] and not x["trade"]]
        mt = collections.Counter(x["match"] for x in tr)
        n, nt, c, nm = svc_shares(x["svc"] for x in tr)
        tips = collections.defaultdict(list)
        for x in tr:
            for k, v in x["svc"].items(): tips[k].append(v)
        cups = [x["cup"] for x in tr if x["cup"] is not None]
        payers = collections.Counter(x["payer"] for x in tr)
        na = c.get(ASTRA, 0); nb = c.get(BEAM, 0)
        wrows.append(dict(label=lab, wallet=w, succ=n, buys=sum(1 for x in tr if x["buy"]), sells=sum(1 for x in tr if x["sell"]),
                          failed=len(fail), failed_as_payer=sum(1 for x in fail if x["match"] == "payer"), succ_other=len(oth),
                          match_payer=mt.get("payer", 0), match_user=mt.get("user", 0), match_both=mt.get("both", 0),
                          distinct_payers=len(payers), tipped=nt, multi=nm, astra=na, beam=nb,
                          astra_pct_tipped=round(pct(na, nt), 1), beam_pct_tipped=round(pct(nb, nt), 1),
                          services={k: v for k, v in c.most_common()}, service_pct={k: round(pct(v, n), 1) for k, v in c.most_common()},
                          med_tip={k: med(v) for k, v in tips.items()}, med_cup=med(cups), cup_null=sum(1 for x in tr if x["cup"] is None),
                          med_fee=med([x["fee"] for x in tr]), verdict=verdict(nt, na) if n else "inactive (0 landed pump txs)"))

    # ---------------------------------------------------------------- top race winners
    top = sorted(first_by_user.items(), key=lambda kv: -len(kv[1]))[:a.top]
    trows = []
    for u, lst in top:
        wins = [b for b, s in lst]; same = sum(1 for b, s in lst if b[0] == s)
        wn, wt, wc, wm = svc_shares(b[7] for b in wins)
        rr = list(racer_by_user[u].values()); rn, rt, rc, rm = svc_shares(b[7] for b in rr)
        ua = U.get(u, [0, 0, 0, 0, 0, {}]); uc = collections.Counter(ua[5])
        tip_vals = collections.defaultdict(list)
        for b in rr:
            for k, v in b[7]: tip_vals[k].append(v)
        trows.append(dict(user=u, label=LABEL.get(u, ""), wins=len(wins), same_slot_wins=same, same_pct=round(pct(same, len(wins)), 1),
                          win_payers=len({b[4] for b in wins}), racer_txs=len(rr),
                          wins_tipped=wt, wins_astra=wc.get(ASTRA, 0), wins_mix=mix_str(wc, wn),
                          racer_tipped=rt, racer_astra=rc.get(ASTRA, 0), racer_beam=rc.get(BEAM, 0), racer_mix=mix_str(rc, rn),
                          all_succ=ua[0], all_buys=ua[1], all_sells=ua[2], all_tipped=ua[3], all_multi=ua[4], all_astra=uc.get(ASTRA, 0),
                          all_beam=uc.get(BEAM, 0), all_mix=mix_str(uc, ua[0]), failed_as_payer=FP.get(u, 0),
                          med_cup=med([b[8] for b in rr]), med_tip={k: med(v) for k, v in tip_vals.items()},
                          astra_pct_tipped=round(pct(uc.get(ASTRA, 0), ua[3]), 1), verdict=verdict(ua[3], uc.get(ASTRA, 0))))

    # ---------------------------------------------------------------- plain answer
    cls = {}
    for r in wrows:
        if r["label"].startswith("ours"): continue
        cls[r["wallet"]] = (r["label"], r["verdict"], r["astra_pct_tipped"], r["tipped"], "named", r["beam_pct_tipped"])
    for r in trows:
        if r["user"] not in cls:
            cls[r["user"]] = (r["user"][:8], r["verdict"], r["astra_pct_tipped"], r["all_tipped"], "top-race",
                              round(pct(r["all_beam"], r["all_tipped"]), 1))
    active = {k: v for k, v in cls.items() if not v[1].startswith("inactive")}
    n_rely = sum(1 for v in active.values() if v[1].startswith("RELIES")); n_use = sum(1 for v in active.values() if v[1].startswith("uses"))
    n_never = len(active) - n_rely - n_use
    tot_tipped = T["tipped"]; tot_trade = T["trade_txs"]

    # ---------------------------------------------------------------- unknown destinations
    unk = []
    for k, v in UN.items():
        unk.append(dict(account=k, n_notip_buys=v[0], n_tipped_buys=v[1], share_notip=round(pct(v[0], T["notip_buy_txs"]), 2),
                        share_tipped=round(pct(v[1], T["tipped_buy_txs"]), 2), payers_sampled=v[4],
                        med_delta=med(v[2]), med_ratio_to_buy_sol=med(v[3]), round_pct=round(pct(sum(1 for d in v[2] if d % 10000 == 0), len(v[2])), 0)))
    unk.sort(key=lambda x: -x["n_notip_buys"])

    tw = sum(r["wins"] for r in trows)
    rw = sum(r["wins"] for r in trows if r["verdict"].startswith("RELIES")); uw = sum(r["wins"] for r in trows if r["verdict"].startswith("uses"))
    # ---------------------------------------------------------------- write outputs
    gsvc = {k: dict(txs=v, pct_trade=round(pct(v, tot_trade), 2), pct_tipped=round(pct(v, tot_tipped), 2), med_tip=med_counter(svc_tip[k]))
            for k, v in svc_n.most_common()}
    meta = dict(window_utc=[utc(t_start), utc(t_end)], window_pkt=[pkt(t_start), pkt(t_end)], t_start=t_start, t_end=t_end,
                block_time_range=[bmin, bmax], block_time_utc=[utc(bmin), utc(bmax)] if bmin else None,
                chunks=len(chunks_meta), truncated=[c for c in chunks_meta if c["trunc"]], newest_chunk=os.path.basename(newest[1]),
                newest_possibly_partial=partial_newest, overlap=overlap_info, runs=order, dump_sol=a.dump_sol,
                tipmap_accounts=len(TIPNAME), tipmap_services=sorted(set(TIPNAME.values())), secs=round(time.time() - t0))
    race = dict(dumps=len(D), dumps_with_racer=sum(1 for x in D if x["first_user"]), racer_txs=allr[0], ours_first=ours_first,
                ours_racer_txs=len(ours_racer_sigs), agent_first=agent_first, agent_racer_txs=len(agent_racer_sigs),
                agent_dumps=sum(1 for x in D if x["seller"] in NONCOMP),
                all_racers=dict(n=allr[0], tipped=allr[1], multi=allr[3], svc=dict(allr[2].most_common())),
                first=dict(n=fst[0], tipped=fst[1], multi=fst[3], svc=dict(fst[2].most_common())),
                first_same_slot=dict(n=fss[0], tipped=fss[1], multi=fss[3], svc=dict(fss[2].most_common())),
                first_next_slot=dict(n=fs1[0], tipped=fs1[1], multi=fs1[3], svc=dict(fs1[2].most_common())),
                top_wins=tw, top_wins_rely=rw, top_wins_uses=uw)
    out = dict(meta=meta, totals=dict(T), services=gsvc, rec_unmapped_tips=dict(unmapped.most_common(50)), race=race,
               top_racers=trows, wallets=wrows, answer=dict(rely=n_rely, uses=n_use, never=n_never, considered=len(active),
               inactive=[v[0] for v in cls.values() if v[1].startswith("inactive")],
               detail={k: dict(label=v[0], verdict=v[1], astra_pct_tipped=v[2], tipped=v[3], group=v[4], beam_pct_tipped=v[5])
                       for k, v in cls.items()}),
               unknown_dest_top=unk[:40], chunks=sorted(chunks_meta, key=lambda c: c["file"]))
    json.dump(out, open(os.path.join(a.out, "census.json"), "w"), indent=1, default=str)
    with open(os.path.join(a.out, "wallets.csv"), "w", newline="") as f:
        cols = ["label", "wallet", "succ", "buys", "sells", "failed", "failed_as_payer", "succ_other", "match_payer", "match_user",
                "match_both", "distinct_payers", "tipped", "multi", "astra", "beam", "astra_pct_tipped", "beam_pct_tipped",
                "med_cup", "cup_null", "med_fee", "verdict", "service_pct", "med_tip"]
        wr = csv.DictWriter(f, cols, extrasaction="ignore"); wr.writeheader()
        for r in wrows: wr.writerow({**r, "service_pct": json.dumps(r["service_pct"]), "med_tip": json.dumps(r["med_tip"])})
    with open(os.path.join(a.out, "race_top.csv"), "w", newline="") as f:
        cols = list(trows[0].keys()) if trows else ["user"]
        wr = csv.DictWriter(f, cols); wr.writeheader()
        for r in trows: wr.writerow({**r, "med_tip": json.dumps(r["med_tip"])})
    with gzip.open(os.path.join(a.out, "dumps.csv.gz"), "wt", newline="") as f:
        cols = list(D[0].keys()) if D else ["slot"]
        wr = csv.DictWriter(f, cols); wr.writeheader()
        for x in sorted(D, key=lambda x: (x["slot"], x["idx"], x["j"])): wr.writerow(x)
    with gzip.open(os.path.join(a.out, "users.csv.gz"), "wt", newline="") as f:
        wr = csv.writer(f); wr.writerow(["identity", "succ_pump_txs", "buys", "sells", "tipped", "multi", "astra", "beam", "failed_as_payer",
                                         "first_racer_wins", "racer_txs", "services"])
        for k, v in sorted(U.items(), key=lambda kv: -kv[1][0])[:20000]:
            wr.writerow([k, v[0], v[1], v[2], v[3], v[4], v[5].get(ASTRA, 0), v[5].get(BEAM, 0), FP.get(k, 0),
                         len(first_by_user.get(k, ())), len(racer_by_user.get(k, ())), json.dumps(v[5])])
    with open(os.path.join(a.out, "unknown_dest.csv"), "w", newline="") as f:
        cols = ["account", "n_notip_buys", "n_tipped_buys", "share_notip", "share_tipped", "payers_sampled", "med_delta",
                "med_ratio_to_buy_sol", "round_pct"]
        wr = csv.DictWriter(f, cols); wr.writeheader()
        for r in unk[:200]: wr.writerow(r)

    # ---------------------------------------------------------------- print tables
    P = io.StringIO()
    def p(*x): print(*x, file=P)
    p(f"ASTRALANE CENSUS  window {meta['window_utc'][0]} .. {meta['window_utc'][1]}  =  {meta['window_pkt'][0]} .. {meta['window_pkt'][1]}")
    if bmin: p(f"  block times seen {utc(bmin)} .. {utc(bmax)} ({pkt(bmin)} .. {pkt(bmax)}); chunks {len(chunks_meta)} from {', '.join(order)}")
    ov = ", ".join("%s->%s %s sigs" % (o["older"], o["newer"], format(o["sigs"], ",")) for o in overlap_info) or "none"
    p(f"  overlap dedupe: {ov}; skipped {T['dup_skipped']:,} duplicate lines")
    p(f"  truncated chunks: {len(meta['truncated'])}; newest chunk {meta['newest_chunk']} possibly partial: {partial_newest}")
    p("")
    p("1) SANITY (MEASURED)")
    p(f"  lines {T['lines']:,}  failed {T['failed']:,} ({pct(T['failed'], T['lines']):.1f}%, tips rolled back = unclassifiable)  "
      f"successful non-trade {T['succ_nontrade']:,}")
    p(f"  successful pump bonding-curve trade txs {tot_trade:,} (buy txs {T['trade_buy_txs']:,}, sell txs {T['trade_sell_txs']:,}); "
      f"with a known tip {tot_tipped:,} = {pct(tot_tipped, tot_trade):.1f}%; multi-service {T['multi']:,} = {pct(T['multi'], tot_tipped):.1f}% of tipped")
    p(f"  recorder tips to accounts outside our map: {sum(unmapped.values()):,} txs {dict(unmapped.most_common(5))}")
    p("  services over ALL successful pump trade txs (MEASURED; % of all / % of tipped; median tip lamports):")
    for k, v in list(gsvc.items())[:16]:
        p(f"    {k + (' (Beam, maybe Astralane)' if k == BEAM else ''):38s} {v['txs']:>9,}  {v['pct_trade']:5.1f}% / {v['pct_tipped']:5.1f}%  med {fmt_l(v['med_tip'])}")
    p("")
    p("2) NAMED WALLETS (MEASURED; matched as fee payer OR TradeEvent user; failed = wallet among signers)")
    p(f"  {'wallet':9s} {'succ':>6s} {'buy':>6s} {'sell':>6s} {'fail':>7s} {'p/u/both':>14s} {'tip%':>5s} {'astra%tip':>9s} {'beam%tip':>8s} {'multi%':>6s} "
      f"{'medCUpx':>9s}  verdict")
    for r in wrows:
        p(f"  {r['label']:9s} {r['succ']:>6,} {r['buys']:>6,} {r['sells']:>6,} {r['failed']:>7,} "
          f"{str(r['match_payer']) + '/' + str(r['match_user']) + '/' + str(r['match_both']):>14s} {pct(r['tipped'], r['succ']):5.0f} "
          f"{r['astra_pct_tipped']:9.1f} {r['beam_pct_tipped']:8.1f} {pct(r['multi'], r['tipped']):6.1f} {fmt_l(r['med_cup']):>9s}  {r['verdict']}")
    p("  services per wallet (% of its successful pump txs; median tip lamports):")
    for r in wrows:
        if not r["succ"]: continue
        top_s = sorted(r["services"].items(), key=lambda kv: -kv[1])[:5]
        p(f"    {r['label']:9s} " + ("; ".join(f"{k} {pct(v, r['succ']):.0f}% (med {fmt_l(r['med_tip'][k])})" for k, v in top_s) or "no known tip")
          + f"; no tip {pct(r['succ'] - r['tipped'], r['succ']):.0f}%")
    p("")
    p(f"3) THE RACE (MEASURED): dumps = bonding-curve sells >= {a.dump_sol:g} SOL; racers = other users' buys of that mint after it, same slot or slot+1")
    p(f"  dumps {len(D):,}; with >=1 competitor racer {race['dumps_with_racer']:,}; unique competitor racer txs {allr[0]:,}; "
      f"our first-racer wins {ours_first:,} (our racer txs {len(ours_racer_sigs):,})")
    p(f"  pump Mayhem agent (not a competitor; excluded from racers): its dumps {race['agent_dumps']:,} (kept as dumps), "
      f"first-after-dump {agent_first:,}, racer txs {len(agent_racer_sigs):,}")
    def line(name, sh):
        n, nt, c, nm = sh
        return (f"  {name:28s} n={n:>7,}  tipped {pct(nt, n):5.1f}%  astralane {pct(c.get(ASTRA, 0), n):5.1f}% of all / {pct(c.get(ASTRA, 0), nt):5.1f}% of tipped  "
                f"beam {pct(c.get(BEAM, 0), n):4.1f}%  multi {pct(nm, nt):4.1f}%\n      mix: {mix_str(c, n, 8)}")
    p(line("(a) all racer txs", allr)); p(line("(b) first racer per dump", fst)); p(line("(c) first racer, same slot", fss))
    p(line("(c') first racer, slot+1", fs1))
    p(f"  first racers in the same slot: {fss[0]:,} of {fst[0]:,} = {pct(fss[0], fst[0]):.1f}%")
    p("")
    p(f"4) TOP {a.top} RACE WINNERS by first-after-dump wins (MEASURED; mixes = % of txs; 'all' = every successful pump tx of the wallet in the window)")
    p(f"  {'wallet':12s} {'wins':>5s} {'same%':>5s} {'payers':>6s} {'racer':>6s} {'astra%win':>9s} {'all_tx':>7s} {'tip%':>5s} {'astra%tip':>9s} {'beam%tip':>8s} {'fail(p)':>8s} {'medCUpx':>9s}  verdict / win mix")
    for r in trows:
        p(f"  {(r['label'] or r['user'][:8]):12s} {r['wins']:>5,} {r['same_pct']:5.0f} {r['win_payers']:>6,} {r['racer_txs']:>6,} "
          f"{pct(r['wins_astra'], r['wins']):9.1f} {r['all_succ']:>7,} {pct(r['all_tipped'], r['all_succ']):5.0f} {r['astra_pct_tipped']:9.1f} "
          f"{pct(r['all_beam'], r['all_tipped']):8.1f} {r['failed_as_payer']:>8,} {fmt_l(r['med_cup']):>9s}  {r['verdict']} | {r['wins_mix']}")
    p(f"  top {a.top} hold {tw:,} of {fst[0]:,} first-racer wins ({pct(tw, fst[0]):.1f}%); wallets that RELY on Astralane hold {rw:,} ({pct(rw, fst[0]):.1f}%), "
      f"that USE it {uw:,} ({pct(uw, fst[0]):.1f}%)")
    p("")
    p("5) PLAIN ANSWER")
    p(f"  of {sum(1 for v in cls.values() if v[4] == 'named')} named competitors + {sum(1 for v in cls.values() if v[4] == 'top-race')} more top-{a.top} race winners "
      f"(= {len(cls)} wallets; {len(cls) - len(active)} inactive in the window): {n_rely} rely on Astralane (>=50% of tipped txs), "
      f"{n_use} use it sometimes (5-50%), {n_never} never/<5%  (MEASURED counts, thresholds as briefed)")
    for k, v in cls.items():
        p(f"    {v[0]:10s} {k:44s} {v[4]:8s} {v[1]:30s} astra {v[2]:5.1f}% of {v[3]:>6,} tipped txs; beam {v[5]:4.1f}%")
    p(f"  Astralane share: first-racer wins {pct(fst[2].get(ASTRA, 0), fst[0]):.1f}% of all / {pct(fst[2].get(ASTRA, 0), fst[1]):.1f}% of tipped; "
      f"same-slot wins {pct(fss[2].get(ASTRA, 0), fss[0]):.1f}% / {pct(fss[2].get(ASTRA, 0), fss[1]):.1f}%; "
      f"vs all pump txs {pct(svc_n.get(ASTRA, 0), tot_trade):.1f}% / {pct(svc_n.get(ASTRA, 0), tot_tipped):.1f}% (MEASURED)")
    p("")
    p("6) UNKNOWN-DESTINATION SCREEN (SOL-quote successful buy txs; non-signer, non-tip positive deltas; lift = share in no-tip buys / share in tipped buys;")
    p("   tip-like = lift >= 3 (shows up when no known tip is paid); fee-like = ratio to buy size ~constant, lift ~1)")
    p(f"  no-known-tip buy txs {T['notip_buy_txs']:,}; tipped buy txs {T['tipped_buy_txs']:,}")
    def lift_of(r): return (r["share_notip"] / r["share_tipped"]) if r["share_tipped"] else float("inf")
    def unk_line(r):
        return (f"    {r['account']:44s} notip {r['n_notip_buys']:>8,} ({r['share_notip']:5.1f}%) tipped {r['n_tipped_buys']:>7,} ({r['share_tipped']:5.1f}%) "
                f"lift {lift_of(r):6.1f} payers~{r['payers_sampled']:>5,} med {fmt_l(r['med_delta'])} ratio {r['med_ratio_to_buy_sol'] or 0:.4f} round {r['round_pct']:.0f}%")
    p("  tip-like candidates (lift >= 3):")
    for r in [r for r in unk if lift_of(r) >= 3][:10]: p(unk_line(r))
    p("  most common overall (for reference):")
    for r in unk[:4]: p(unk_line(r))
    p(f"\n  {time.time() - t0:.0f}s; outputs in {a.out}")
    txt = P.getvalue(); print(txt)
    open(os.path.join(a.out, "summary.txt"), "w").write(txt)

if __name__ == "__main__":
    main()
