#!/usr/bin/env python3
# Day arrays for the LLM pattern search (read-only). For R1 / R2 / R3: every bonding-curve trade of the day's standard
# (non-mayhem) launches, in chain order per token, with CAUSAL features computed at that trade (only trades <= it):
# event (side, size, price move, wallet type), token state (age, curve SOL, ATH ratio, returns over 1/3/10/30/100 slots,
# quiet slots), window stats over the last 1/3/10/30 slots, wallet-type flow (family / bot / fresh / creator / insider),
# creator and insider sold fractions, totals, PKT hour, launch labels (Haiku launch labels file).
# Wallet types: creator / create-slot insider / family F1..F10 and bot from R2-ONLY lists (p0_lists.py) / fresh = first
# seen in the day's data < 10 min before / other.  Stage A parses phase-A rows per bucket and collects first-seen;
# stage B computes features. -> /home/moiz/sniper-data/strategies/patterns/day_{R1,R2,R3}.npz (+ _meta.json)
import sys, os, json, gzip, glob, zlib, pickle, hashlib, collections, bisect
import numpy as np
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; PO = "/home/moiz/sniper-data/strategies/patterns"; TMP = f"{PO}/tmp"
RUNS = {"R1": ("run_20261021_2207", [f"{D}/phaseA"]), "R2": ("run_20261022_1543", [f"{D}/phaseA_fwd"]),
        "R3": ("run_20261023_1426", [f"{D}/phaseA_r3", "/home/moiz/sniper-data/strategies/phaseA_r3tail"])}
SMS = 212.0; GRADV = 113e9
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize.json")).items()}
SLACK = sorted(sl for _, sl, _ in json.load(open("/home/moiz/sniper/ops/overnight/verify2/work/a8_slack.json"))["rows"])
def slack(sig):
    h = int(hashlib.sha256(("dip" + sig).encode()).hexdigest()[:8], 16) / 2 ** 32
    return min(SLACK[min(len(SLACK) - 1, int(h * len(SLACK)))], 1e6)
THEMES = ["animal", "character_meme", "person_celebrity", "politics", "ai_tech", "crypto_finance", "news_event", "sports", "food",
          "brand_product", "nsfw_vulgar", "gibberish_random", "other"]
XL = ["none", "post", "profile", "community"]
WT = {"other": 0, "creator": 1, "insider": 2, "fresh": 3, "bot": 4, **{f"F{k}": 10 + k for k in range(1, 11)}}
FEATS = ["ev_buy", "sol", "move", "wt", "w_first", "age", "curve", "ath_r", "from_bun", "ret1", "ret3", "ret10", "ret30", "ret100", "quiet",
         "nb1", "ns1", "bsol1", "ssol1", "maxb1", "maxs1"]
for w in (3, 10, 30):
    FEATS += [f"nb{w}", f"ns{w}", f"bsol{w}", f"ssol{w}", f"net{w}", f"nw{w}", f"bigb{w}", f"bigs{w}", f"maxb{w}", f"maxs{w}", f"dd{w}"]
FEATS += ["fam_b10", "fam_s10", "bot_b10", "fresh_b10", "dev_s30", "ins_s30", "dev_sold", "ins_sold", "ntr", "nwal", "peak", "hour",
          "theme", "x", "eff", "fun", "rw", "cpy", "red", "bid", "nbot_hold", "fam_hold"]
FI = {k: i for i, k in enumerate(FEATS)}

def load_launches(run):
    L = {}
    for l in open(os.path.join(D, RUNS[run][0], "launches.jsonl")):
        try: c = json.loads(l)
        except Exception: continue
        if c.get("err") or "InitializeMayhemState" in (c.get("ixn") or []): continue
        L[c["mint"]] = (c["slot"], c.get("idx") or 0, c.get("creator") or c.get("user"), c.get("user"), c.get("sig"), c.get("bt"))
    return L

def arrival(s, i): return s * SMS + i / max(SS.get(s, 400), i + 1) * SMS

def stage_a(key):
    run, b = key
    L = load_launches(run); mints = {m for m in L if zlib.crc32(m.encode()) % 256 == b}
    out = collections.defaultdict(list); seen = set()
    for d in RUNS[run][1]:
        for f in glob.glob(f"{d}/b{b:03d}/*.jsonl.gz"):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    e = line.index('"', 6); m = line[6:e]
                    if m not in mints: continue
                    r = json.loads(line)
                    if r[12] or (r[5], r[13]) in seen: continue
                    seen.add((r[5], r[13]))
                    fr = ((r[22] or 95) + (r[23] or 30)) / 1e4
                    out[m].append((r[2], r[3], r[13], r[4], slack(r[5]) if r[15] == 1 else 0.0, r[14], r[15] == 1, r[16], r[17], r[18], r[19], fr))
            except (EOFError, OSError, zlib.error, ValueError): pass
    keep = {}; first = {}
    for m, tr in out.items():
        tr.sort(key=lambda t: (t[0], t[1], t[2]))
        if any(t[9] < 25e9 or t[9] > 200e9 or not t[10] for t in tr[:50]): continue
        keep[m] = (L[m], tr)
        for t in tr:
            k = (t[0], t[1])
            if t[5] not in first or k < first[t[5]]: first[t[5]] = k
    with open(f"{TMP}/{run}_{b:03d}.pkl", "wb") as f: pickle.dump(keep, f, protocol=4)
    return run, first

G = {}
def init_b(run):
    G["first"] = pickle.load(open(f"{TMP}/{run}_first.pkl", "rb"))
    G["lists"] = json.load(open(f"{PO}/lists_r2.json"))
    lab = {}
    for l in open("/home/moiz/sniper-data/llm/launch_labels/labels.jsonl"):
        o = json.loads(l); lab[o["mint"]] = o
    G["lab"] = lab
    G["bids"] = {u: (v[0], v[1]) for u, v in json.load(open(f"{PO}/botids.json")).items()}

def stage_b(key):
    run, b = key
    keep = pickle.load(open(f"{TMP}/{run}_{b:03d}.pkl", "rb"))
    first, lists, lab, bids = G["first"], G["lists"], G["lab"], G["bids"]
    cols = {k: [] for k in ("tok", "s", "i", "arr", "buy", "sol", "tokn", "vsol", "vtok", "fr", "slack", "wt", "bt", "bid", "uid")}
    FM = []; mints = []; meta = []
    for m, (c, tr) in sorted(keep.items()):
        S0, cidx, creator, signer, csig, cbt = c
        n = len(tr); ti = len(mints); mints.append(m)
        Sarr = np.array([t[0] for t in tr], np.int64)
        buy = np.array([t[6] for t in tr], bool); sol = np.array([t[7] for t in tr], float); tok = np.array([t[8] for t in tr], float)
        V = np.array([t[9] for t in tr], float); T = np.array([t[10] for t in tr], float)
        Vpre = np.where(buy, V - sol, V + sol); Tpre = np.where(buy, T + tok, T - tok)
        ppost = V / T; ppre = np.where(Tpre > 0, Vpre / np.maximum(Tpre, 1), ppost)
        users = [t[5] for t in tr]
        ins = set(t[5] for t in tr if t[0] == S0 and t[6]) - {creator, signer}
        wt = np.zeros(n, np.int8)
        for k, u in enumerate(users):
            if u == creator or u == signer: wt[k] = 1
            elif u in ins: wt[k] = 2
            else:
                L_ = lists.get(u)
                if L_ and L_.startswith("F"): wt[k] = WT[L_]
                elif L_ == "bot": wt[k] = 4
                else:
                    fs = first.get(u)
                    if fs and tr[k][0] - fs[0] <= 2830: wt[k] = 3
        isfam = wt >= 11; isbot = wt == 4; isfresh = wt == 3; iscre = wt == 1; isins = wt == 2
        # bundle end price
        kb = int(np.searchsorted(Sarr, S0, side="right")) - 1
        p_bun = ppost[kb] if kb >= 0 else ppre[0]
        ath = np.maximum.accumulate(ppost)
        # returns over w slots: price after the last trade with slot <= s - w (else the first pre-state)
        rets = {}
        for w in (1, 3, 10, 30, 100):
            j = np.searchsorted(Sarr, Sarr - w, side="right") - 1
            pw = np.where(j >= 0, ppost[np.maximum(j, 0)], ppre[0])
            rets[w] = (ppost / pw - 1) * 100
        quiet = np.empty(n); quiet[0] = Sarr[0] - S0; quiet[1:] = Sarr[1:] - Sarr[:-1]
        cb = np.concatenate([[0], np.cumsum(buy)]); cs = np.concatenate([[0], np.cumsum(~buy)])
        cbs = np.concatenate([[0], np.cumsum(np.where(buy, sol, 0))]); css = np.concatenate([[0], np.cumsum(np.where(~buy, sol, 0))])
        cbb = np.concatenate([[0], np.cumsum(buy & (sol >= 0.5e9))]); cbsg = np.concatenate([[0], np.cumsum((~buy) & (sol >= 0.5e9))])
        cfb = np.concatenate([[0], np.cumsum(isfam & buy)]); cfs = np.concatenate([[0], np.cumsum(isfam & ~buy)])
        cbot = np.concatenate([[0], np.cumsum(isbot & buy)]); cfr = np.concatenate([[0], np.cumsum(isfresh & buy)])
        cdev = np.concatenate([[0], np.cumsum(np.where(iscre & ~buy, sol, 0))]); cins = np.concatenate([[0], np.cumsum(np.where(isins & ~buy, sol, 0))])
        idx = np.arange(n)
        F = np.zeros((n, len(FEATS)), np.float32)
        F[:, FI["ev_buy"]] = buy; F[:, FI["sol"]] = sol / 1e9; F[:, FI["move"]] = (ppost / ppre - 1) * 100; F[:, FI["wt"]] = wt
        F[:, FI["age"]] = Sarr - S0; F[:, FI["curve"]] = V / 1e9; F[:, FI["ath_r"]] = ppost / ath; F[:, FI["from_bun"]] = ppost / p_bun
        for w in (1, 3, 10, 30, 100): F[:, FI[f"ret{w}"]] = rets[w]
        F[:, FI["quiet"]] = quiet
        for w in (1, 3, 10, 30):
            lo = np.searchsorted(Sarr, Sarr - w + 1, side="left")
            hi = idx + 1
            nb = cb[hi] - cb[lo]; ns = cs[hi] - cs[lo]; bs = (cbs[hi] - cbs[lo]) / 1e9; ss = (css[hi] - css[lo]) / 1e9
            F[:, FI[f"nb{w}"]] = nb; F[:, FI[f"ns{w}"]] = ns; F[:, FI[f"bsol{w}"]] = bs; F[:, FI[f"ssol{w}"]] = ss
            mb = np.zeros(n); msl = np.zeros(n); dd = np.zeros(n); nw = np.zeros(n)
            for k in range(n):
                a = lo[k]
                if k - a < 64:
                    seg_b = [sol[q] for q in range(a, k + 1) if buy[q]]; seg_s = [sol[q] for q in range(a, k + 1) if not buy[q]]
                    mb[k] = max(seg_b) / 1e9 if seg_b else 0; msl[k] = max(seg_s) / 1e9 if seg_s else 0
                    if w >= 3:
                        pm = max(max(ppost[a:k + 1]), max(ppre[a:k + 1])); dd[k] = (1 - ppost[k] / pm) * 100 if pm > 0 else 0
                        nw[k] = len(set(users[a:k + 1]))
                else:
                    sb = sol[a:k + 1]; bb = buy[a:k + 1]
                    mb[k] = sb[bb].max() / 1e9 if bb.any() else 0; msl[k] = sb[~bb].max() / 1e9 if (~bb).any() else 0
                    if w >= 3:
                        pm = max(ppost[a:k + 1].max(), ppre[a:k + 1].max()); dd[k] = (1 - ppost[k] / pm) * 100 if pm > 0 else 0
                        nw[k] = len(set(users[a:k + 1]))
            F[:, FI[f"maxb{w}"]] = mb; F[:, FI[f"maxs{w}"]] = msl
            if w >= 3:
                F[:, FI[f"net{w}"]] = bs - ss; F[:, FI[f"nw{w}"]] = nw; F[:, FI[f"bigb{w}"]] = cbb[hi] - cbb[lo]; F[:, FI[f"bigs{w}"]] = cbsg[hi] - cbsg[lo]; F[:, FI[f"dd{w}"]] = dd
            if w == 10:
                F[:, FI["fam_b10"]] = cfb[hi] - cfb[lo]; F[:, FI["fam_s10"]] = cfs[hi] - cfs[lo]; F[:, FI["bot_b10"]] = cbot[hi] - cbot[lo]; F[:, FI["fresh_b10"]] = cfr[hi] - cfr[lo]
            if w == 30:
                F[:, FI["dev_s30"]] = (cdev[hi] - cdev[lo]) / 1e9; F[:, FI["ins_s30"]] = (cins[hi] - cins[lo]) / 1e9
        # creator / insider sold fractions, first trade of wallet, distinct wallets so far
        dvb = dvs = ib = is_ = 0.0; seen_u = set(); seen_ut = set()
        bidv = np.array([bids[u][0] if u in bids else 0 for u in users], np.int16)
        bpos = {}; bpk = {}; nhold = 0; fhold = 0
        for k in range(n):
            bk = bidv[k]
            if bk:
                was = bpos.get(bk, 0) > 0.01 * bpk.get(bk, 1)
                bpos[bk] = bpos.get(bk, 0) + (tok[k] if buy[k] else -tok[k]); bpk[bk] = max(bpk.get(bk, 0), bpos[bk])
                now = bpos[bk] > 0.01 * bpk[bk]
                if now != was:
                    d = 1 if now else -1; nhold += d
                    if bids[users[k]][1].startswith("F"): fhold += d
            F[k, FI["bid"]] = bk; F[k, FI["nbot_hold"]] = nhold; F[k, FI["fam_hold"]] = fhold
            if iscre[k]:
                if buy[k]: dvb += tok[k]
                else: dvs += tok[k]
            if isins[k]:
                if buy[k]: ib += tok[k]
                else: is_ += tok[k]
            F[k, FI["dev_sold"]] = min(dvs / dvb, 1.0) if dvb > 0 else 0
            F[k, FI["ins_sold"]] = min(is_ / ib, 1.0) if ib > 0 else 0
            F[k, FI["w_first"]] = users[k] not in seen_u
            seen_u.add(users[k]); F[k, FI["nwal"]] = len(seen_u)
        F[:, FI["ntr"]] = idx + 1; F[:, FI["peak"]] = np.maximum.accumulate(V) / 1e9
        F[:, FI["hour"]] = (((np.array([t[3] or cbt or 0 for t in tr]) + 5 * 3600) // 3600) % 24)
        lb = lab.get(m) or {}
        F[:, FI["theme"]] = THEMES.index(lb["th"]) if lb.get("th") in THEMES else -1
        F[:, FI["x"]] = XL.index(lb["x"]) if lb.get("x") in XL else -1
        for k_ in ("eff", "fun", "rw", "cpy", "red"):
            v = lb.get(k_); F[:, FI[k_]] = v if isinstance(v, (int, float)) else -1
        FM.append(F)
        cols["tok"].append(np.full(n, ti, np.int32)); cols["s"].append(Sarr); cols["i"].append(np.array([t[1] for t in tr], np.int32))
        cols["arr"].append(np.array([arrival(t[0], t[1]) for t in tr])); cols["buy"].append(buy.astype(np.int8)); cols["sol"].append(sol)
        cols["tokn"].append(tok); cols["vsol"].append(V); cols["vtok"].append(T); cols["fr"].append(np.array([t[11] for t in tr], np.float32))
        cols["slack"].append(np.array([t[4] for t in tr], np.float32)); cols["wt"].append(wt); cols["bt"].append(np.array([t[3] or 0 for t in tr], np.int64)); cols["bid"].append(bidv)
        cols["uid"].append(np.array([zlib.crc32(u.encode()) for u in users], np.int64))
        meta.append(dict(m=m, S0=S0, cbt=cbt, creator=creator, n=n, p0=float(ppre[0])))
    if not mints:
        return run, b, 0
    np.savez(f"{TMP}/{run}_{b:03d}.npz", F=np.concatenate(FM), **{k: np.concatenate(v) for k, v in cols.items()})
    json.dump(meta, open(f"{TMP}/{run}_{b:03d}.meta.json", "w"))
    return run, b, sum(x["n"] for x in meta)

def concat(run):
    Fs = []; cols = collections.defaultdict(list); meta = []; off = 0
    for b in range(256):
        p = f"{TMP}/{run}_{b:03d}.npz"
        if not os.path.exists(p): continue
        z = np.load(p); mt = json.load(open(f"{TMP}/{run}_{b:03d}.meta.json"))
        Fs.append(z["F"])
        for k in z.files:
            if k == "F": continue
            cols[k].append(z[k] + off if k == "tok" else z[k])
        meta += mt; off += len(mt)
    np.savez(f"{PO}/day_{run}.npz", F=np.concatenate(Fs), **{k: np.concatenate(v) for k, v in cols.items()})
    json.dump(dict(feats=FEATS, themes=THEMES, xl=XL, wt=WT, meta=meta), open(f"{PO}/day_{run}_meta.json", "w"))
    return off

if __name__ == "__main__":
    os.makedirs(TMP, exist_ok=True)
    runs = sys.argv[1:] or ["R2", "R3", "R1"]
    P = int(os.environ.get("PROCS", "9"))
    for run in runs:
        first = {}
        with Pool(P) as p:
            for _, fs in p.imap_unordered(stage_a, [(run, b) for b in range(256)]):
                for u, k in fs.items():
                    if u not in first or k < first[u]: first[u] = k
        pickle.dump(first, open(f"{TMP}/{run}_first.pkl", "wb"), protocol=4)
        tot = 0
        with Pool(P, initializer=init_b, initargs=(run,)) as p:
            for _, b, n in p.imap_unordered(stage_b, [(run, b) for b in range(256)]): tot += n
        nm = concat(run)
        print(f"{run}: {tot} trades, {nm} tokens", flush=True)
