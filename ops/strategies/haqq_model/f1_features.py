#!/usr/bin/env python3
"""HAQQ_MODEL step 1 (read-only, offline): per-token causal features at fixed decision times after create.
Tape: /home/moiz/sniper-data/haqq_model/tab, multi-day (10-23 19:26 to 10-27 23:20 PKT), real/decode.py + build.py over the host's
recording copies. Metadata: collect/run_*/launches.jsonl (name, symbol, uri, create tx fee, ixn).
Unit: one create. Decision slot D = create slot + n, with n in NS. Label y: haqq (user or signer) traded the mint anywhere on the tape.
Causality:
  * token features use only trades with slot <= D, with haqq's rows REMOVED;
  * history features (creator, wallets, haqq's activity on other tokens) are expanding: token blocks of 1 h; a past token enters the
    history only if it was created >= 10 min before the block start; its "haqq traded it" flag counts only once haqq's first trade
    on it is before the block start; haqq's activity counters use his trades (other mints) with block time < the token's create time.
Out: DATA/feat_n<n>.npz (X, names, y, meta arrays)."""
import json, time, collections, glob, re, math, sys
import numpy as np
DATA = "/home/moiz/sniper-data/haqq_model"; TAB = f"{DATA}/tab"
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
NS = (0, 5, 14, 24, 47)
HIST_SLOTS = 47                         # a history token's "early traders" = traders in its first 47 slots (~10 s)
SPS = 0.2118
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))


def main():
    t0 = time.time()
    ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    h = idm[HAQQ]
    T = np.load(f"{TAB}/trades.npy")
    S = np.load(f"{TAB}/slots.npy"); sbt = S["bt"].astype(np.int64)
    # coverage bins (5 min, share of slots recorded)
    b_lo = int(sbt.min()) // 300 * 300; nb = (int(sbt.max()) - b_lo) // 300 + 1
    cov = np.bincount((sbt - b_lo) // 300, minlength=nb) / (300 / SPS)
    t_end = int(sbt.max())
    # creates
    CR = json.load(open(f"{TAB}/creates.json"))
    meta = {}
    for f in sorted(glob.glob("/home/moiz/sniper-data/collect/run_2026102[34567]_*/launches.jsonl")):
        for l in open(f):
            try: c = json.loads(l)
            except Exception: continue
            if c.get("mint") and c["mint"] not in meta:
                meta[c["mint"]] = (c.get("name") or "", c.get("symbol") or "", c.get("uri") or "", int(c.get("fee") or 0), c.get("ixn") or [])
    print(f"tape {len(T):,} trades, creates {len(CR):,}, launch meta {len(meta):,} ({time.time() - t0:.0f}s)", flush=True)
    # per-mint spans (T is chain ordered; a stable sort by mint keeps that order inside a mint)
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, st_ = np.unique(T["mint"], return_index=True); en_ = np.append(st_[1:], len(T))
    span = {int(m): (int(a), int(e)) for m, a, e in zip(um, st_, en_)}
    ishq = (T["user"] == h) | (T["signer"] == h)
    # haqq: first trade per mint, and his trade times (all mints) for activity counters
    hq_rows = np.flatnonzero(ishq)
    hq_first = {}
    for r in hq_rows.tolist():
        m = int(T["mint"][r]); b = int(T["bt"][r])
        if m not in hq_first or b < hq_first[m][0]: hq_first[m] = (b, int(T["slot"][r]))
    hq_bt = np.sort(T["bt"][hq_rows].astype(np.int64))
    hq_first_bt_sorted = np.sort(np.array([v[0] for v in hq_first.values()], np.int64))
    print(f"haqq trades {len(hq_rows):,} on {len(hq_first):,} mints ({time.time() - t0:.0f}s)", flush=True)
    fb_ids = {idm[w] for w in FB if w in idm}; coh_ids = {idm[w] for w in COH if w in idm}
    # universe
    toks = []
    for mint, c in CR.items():
        mi = idm.get(mint)
        if mi is None or c.get("slot") is None: continue
        b = int(c["bt"]); bi = (b - b_lo) // 300
        if b > t_end - 900 or bi < 0 or bi + 1 >= nb or cov[bi] < 0.9 or cov[bi + 1] < 0.9: continue
        toks.append((int(c["slot"]), int(c["idx"]), mi, mint, c))
    toks.sort()
    N = len(toks)
    print(f"universe {N:,} tokens {pkt(toks[0][4]['bt'])} -> {pkt(toks[-1][4]['bt'])} ({time.time() - t0:.0f}s)", flush=True)
    create_bt_sorted = np.array([t[4]["bt"] for t in toks], np.int64)
    # ---------------- history state ----------------
    w_n = collections.Counter(); w_k = collections.Counter()      # wallet: early appearances in history tokens / of those, haqq tokens
    c_n = collections.Counter(); c_k = collections.Counter(); c_last = {}; c_vmax = collections.defaultdict(list)
    base = [0, 0]                                                   # history tokens, of which haqq
    pending_k = []                                                  # heap of (haqq first bt, token index) waiting to count as haqq-known
    import heapq
    early_of = {}                                                   # token index -> early traders (history definition)
    creator_of = {}
    hist_ptr = 0
    names = None; rows = {n: [] for n in NS}
    y = np.zeros(N, np.int8); hq_slot = np.full(N, -1, np.int64); cbt = np.zeros(N, np.int64); cslot = np.zeros(N, np.int64)
    mints = []
    block = None

    def tok_trades(mi):
        a, e = span.get(mi, (0, 0)); return a, e

    for i, (cs, cidx, mi, mint, c) in enumerate(toks):
        b = int(c["bt"]); mints.append(mint); cbt[i] = b; cslot[i] = cs
        if mi in hq_first: y[i] = 1; hq_slot[i] = hq_first[mi][1]
        blk = b // 3600 * 3600
        if blk != block:
            block = blk
            # add history tokens created < block - 600
            while hist_ptr < i and toks[hist_ptr][4]["bt"] < block - 600:
                j = hist_ptr; hcs, _, hmi, _, hc = toks[j]
                a, e = tok_trades(hmi)
                sl = T["slot"][a:e]; us = T["user"][a:e]; hqm = ishq[a:e]
                em = (sl <= hcs + HIST_SLOTS) & ~hqm
                cr_id = idm.get(hc.get("creator"), -1)
                ew = set(us[em].tolist()) - {cr_id}
                early_of[j] = ew
                for w in ew: w_n[w] += 1
                base[0] += 1
                # creator
                c_n[cr_id] += 1; c_last[cr_id] = int(hc["bt"])
                vm = T["vsol"][a:e][(T["bt"][a:e] <= int(hc["bt"]) + 300) & ~hqm]
                c_vmax[cr_id].append(float(vm.max()) / 1e9 if len(vm) else 30.0)
                creator_of[j] = cr_id
                if hmi in hq_first: heapq.heappush(pending_k, (hq_first[hmi][0], j))
                hist_ptr += 1
            while pending_k and pending_k[0][0] < block:
                _, j = heapq.heappop(pending_k)
                for w in early_of[j]: w_k[w] += 1
                c_k[creator_of[j]] += 1; base[1] += 1
        prior = (base[1] + 1) / (base[0] + 20)
        # ---------- static features ----------
        cr_id = idm.get(c.get("creator"), -1)
        nm, sy, uri, cfee, ixn = meta.get(mint, ("", "", "", -1, []))
        dom = re.sub(r"^https?://", "", uri).split("/")[0].lower()
        st = dict(
            v2=float(bool(c.get("v2"))), mayhem=float(bool(c.get("mayhem") or c.get("mayhem_ix"))), cashback=float(bool(c.get("cashback"))),
            holder=float(bool(c.get("holder"))), quote_sol=float(c.get("quote") in (None, "11111111111111111111111111111111")),
            cfee_bps=float(c.get("cfee_bps") or 0), payer_ne_creator=float(c.get("payer") != c.get("creator")),
            user_ne_creator=float(c.get("user") != c.get("creator")), init_vsol=float(c.get("vsol") or 0) / 1e9,
            have_meta=float(mint in meta), create_fee=float(cfee) / 1e9 if cfee >= 0 else np.nan, n_ixn=float(len(ixn)),
            ix_buy=float(any(x.startswith("Buy") for x in ixn)), ix_extend=float(any("Extend" in x for x in ixn)),
            name_len=float(len(nm)), sym_len=float(len(sy)), sym_upper=float(sy.isupper()), name_eq_sym=float(nm.strip().lower() == sy.strip().lower()),
            name_nonascii=float(any(ord(ch) > 127 for ch in nm)), name_words=float(len(nm.split())), name_digits=float(any(ch.isdigit() for ch in nm)),
            uri_ipfs=float("ipfs" in dom), uri_j7=float("j7tracker" in dom), uri_pumpfun=float("pump.fun" in dom or "pump.mypinata" in dom or "pumpfun" in dom),
            uri_other=float(bool(dom) and not ("ipfs" in dom or "j7tracker" in dom or "pump" in dom)), uri_len=float(len(uri)),
            hour=float(time.gmtime(b + 18000).tm_hour), minute=float(time.gmtime(b).tm_min),
            # creator history
            cr_prev=float(c_n[cr_id]), cr_prev_hq=float(c_k[cr_id]), cr_rate=(c_k[cr_id] + 20 * prior) / (c_n[cr_id] + 20),
            cr_since=float(b - c_last[cr_id]) if cr_id in c_last else 1e7,
            cr_vmax_mean=float(np.mean(c_vmax[cr_id][-10:])) if c_vmax.get(cr_id) else np.nan,
            cr_vmax_max=float(np.max(c_vmax[cr_id][-10:])) if c_vmax.get(cr_id) else np.nan,
            # market and haqq activity (other mints, strictly before the create time)
            mkt_creates_5m=float(np.searchsorted(create_bt_sorted, b) - np.searchsorted(create_bt_sorted, b - 300)),
            hq_tr_10m=float(np.searchsorted(hq_bt, b) - np.searchsorted(hq_bt, b - 600)),
            hq_tr_60m=float(np.searchsorted(hq_bt, b) - np.searchsorted(hq_bt, b - 3600)),
            hq_new_10m=float(np.searchsorted(hq_first_bt_sorted, b) - np.searchsorted(hq_first_bt_sorted, b - 600)),
            hq_new_60m=float(np.searchsorted(hq_first_bt_sorted, b) - np.searchsorted(hq_first_bt_sorted, b - 3600)),
            hq_since_last=float(b - hq_bt[np.searchsorted(hq_bt, b) - 1]) if np.searchsorted(hq_bt, b) > 0 else 1e5,
            prior=prior)
        # ---------- flow features at each decision slot ----------
        a, e = tok_trades(mi)
        e = a + int(np.searchsorted(T["slot"][a:e], cs + max(NS), side="right"))
        sl = T["slot"][a:e]; keep = ~ishq[a:e]
        for n in NS:
            D = cs + n
            m = keep & (sl <= D)
            us = T["user"][a:e][m]; sg = T["signer"][a:e][m]; bu = T["buy"][a:e][m].astype(bool); so = T["sol"][a:e][m] / 1e9
            vs = T["vsol"][a:e][m]; vt = T["vtok"][a:e][m]; ss = sl[m]
            dev = us == cr_id
            nb_ = int(bu.sum())
            buyers = set(us[bu].tolist()); sellers = set(us[~bu].tolist())
            nondev_b = bu & ~dev
            cs_m = ss == cs
            first_nd = ss[nondev_b]
            ew = set(us.tolist()) - {cr_id}
            rates = [(w_k[w] + 5 * prior) / (w_n[w] + 5) for w in ew]
            ns_ = [w_n[w] for w in ew]
            strong = sum(1 for w in ew if w_n[w] >= 5 and w_k[w] / w_n[w] >= 0.5)
            f = dict(
                n_tr=float(len(us)), n_buy=float(nb_), n_sell=float(len(us) - nb_), n_buyers=float(len(buyers)), n_sellers=float(len(sellers)),
                n_signers=float(len(set(sg.tolist()))), n_user_ne_signer=float((us != sg).sum()),
                buy_sol=float(so[bu].sum()), sell_sol=float(so[~bu].sum()), max_buy=float(so[bu].max()) if nb_ else 0.0,
                dev_buy=float(so[bu & dev].sum()), dev_sell=float(so[~bu & dev].sum()), dev_sold=float((~bu & dev).any()),
                cs_nondev_buys=float((nondev_b & cs_m).sum()), cs_nondev_sol=float(so[nondev_b & cs_m].sum()),
                cs_buyers=float(len(set(us[nondev_b & cs_m].tolist()))),
                first_nd_slot=float(first_nd.min() - cs) if len(first_nd) else 99.0,
                n_slots_active=float(len(np.unique(ss))),
                vsol_now=float(vs[-1]) / 1e9 if len(vs) else float(c.get("vsol") or 30e9) / 1e9,
                px_ratio=float((vs[-1] / max(vt[-1], 1)) / ((c.get("vsol") or 30e9) / (c.get("vtok") or 1.073e15))) if len(vs) else 1.0,
                big_buys=float((so[bu] >= 1.0).sum()), nd_buy_sol=float(so[nondev_b].sum()),
                fb_n=float(len(ew & fb_ids)), coh_n=float(len(ew & coh_ids)),
                w_rate_max=max(rates) if rates else prior, w_rate_mean=float(np.mean(rates)) if rates else prior,
                w_rate_sum=float(np.sum(rates)) if rates else 0.0, w_k_sum=float(sum(w_k[w] for w in ew)),
                w_known=float(sum(1 for x in ns_ if x >= 5)), w_strong=float(strong),
                w_rate_top3=float(np.mean(sorted(rates)[-3:])) if rates else prior,
            )
            if names is None: names = list(st) + list(f)
            rows[n].append([*st.values(), *f.values()])
        if i % 20000 == 0: print(f"  {i:,}/{N:,} {pkt(b)} ({time.time() - t0:.0f}s)", flush=True)
    seen_hq = np.array([hq_slot[i] for i in range(N)])
    for n in NS:
        X = np.array(rows[n], np.float32)
        already = (hq_slot >= 0) & (hq_slot <= cslot + n)
        np.savez(f"{DATA}/feat_n{n}.npz", X=X, names=np.array(names), y=y, bt=cbt, slot=cslot, mint=np.array(mints), hq_first_slot=hq_slot,
                 already=already)
    print(f"done N={N:,} pos={int(y.sum()):,} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
