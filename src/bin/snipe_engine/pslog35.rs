// =====================================================================================================================
// dip35 LOG-ONLY "fam" (owner 11-04, ops/strategies/presend/filters3/bundlewal/REPORT.md; frozen fam >= 26.8249%). Behind
// --presend-live-fam-log, OFF by default: off = nothing of it runs, no record changes, nothing is spawned. NEVER acted on: no arm,
// skip, attempt or exit reads any of it.
//   * fam = % of supply held now by the "bundle family": owners who got tokens in the create slot + owners who got tokens by plain
//     transfer (no TradeEvent); the curve and our wallet out. Bnx6XibY (r53): 4 create-slot bundles -> ~13 wallets ~2.56%, then
//     plain transfers to ~80 fresh wallets that dumped together: fam 46.1% at the arm.
//   * the feed decodes pump trades only (a transfer is invisible), so at every presend_live_arm (T2 and re-arm) a background task
//     reads ALL token accounts of the mint (getProgramAccounts, withContext, dataSlice owner+amount; SPL Token for create, Token-2022
//     for create_v2, the other program when the first has none) and the answer is classified against the detector's on-curve book:
//       create-slot owner = its first on-curve buy in the create slot (the creator's create+buy included);
//       recipient         = a holding > its net on-curve tokens + FAM_TOL (the larger of the net at the arm and at the answer: a
//                           sale the feed saw before the RPC did is not a "receipt"); never traded on curve = net 0.
//     hist "partial": the detector does not follow the token (every holder then looks like a recipient: do not trust fam).
//   * bounded: <= FAM_INFLIGHT reads at once (more: skipped + counted, a record with err "busy"), FAM_TIMEOUT each; never awaited by
//     the decision / send path; not one of the run end's tasks. read_slot > arm_slot is expected (a later snapshot than the study's
//     cutoff): recorded to audit the look-ahead.
//   * record {"ev": "presend_live_fam", w, mint, rearm, fam, cs_pct, recv_n, recv_pct, n_holders, hist, arm_slot, read_slot, lag_ms,
//     hit, thr, prog, err}; a line only on a hit; run_end "dip35_log" {reads, hits, busy, errors, lag_ms_p50}.
// =====================================================================================================================
use super::*;

/// the frozen threshold (% of supply; FROZEN.json fam.thr = 26.8249999999998)
pub const FAM_THR: f64 = 26.825;
/// reads in flight at most (one more is skipped, "busy")
pub const FAM_INFLIGHT: u64 = 4;
/// one read's whole budget (both programs)
pub const FAM_TIMEOUT: Duration = Duration::from_secs(3);
/// a holding above its net on-curve tokens by more than this (raw; 0.001% of supply) came off the curve
pub const FAM_TOL: i64 = 10_000_000_000;
/// recv_n / recv_pct count recipients still holding >= 0.05% (the study's nrecv / precv); fam counts every one
pub const FAM_MINH: i64 = 500_000_000_000;
/// lags kept for the summary's median
const LAG_KEEP: usize = 4096;

/// the detector's on-curve book of a token: (wallet, net on-curve tokens, first buy in the create slot); None: not followed
pub type Book = Option<Vec<(Pk, i64, bool)>>;

/// one read to make (the arm's side)
#[derive(Clone, Debug)]
pub struct FamReq { pub w: u64, pub mint: Pk, pub rearm: bool, pub arm_slot: u64, pub t22: bool, pub curve: Pk, pub at: Instant, pub book: Book }

/// its answer: the program read, (read slot, (owner, amount) per token account) or the error
#[derive(Clone, Debug)]
pub struct FamRes { pub req: FamReq, pub prog: &'static str, pub read: std::result::Result<(u64, Vec<(Pk, u64)>), String> }

/// the classification
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Fam { pub fam: f64, pub cs_pct: f64, pub recv_n: usize, pub recv_pct: f64, pub n_holders: usize }

/// a token account's (owner, amount): SPL Token and Token-2022 share the base layout (mint 0..32, owner 32..64, amount 64..72;
/// Token-2022's extensions start after byte 165). `sliced`: `d` is the RPC's dataSlice {offset 32, length 40}
pub fn acct_parse(d: &[u8], sliced: bool) -> Option<(Pk, u64)> {
    let o = if sliced { 0 } else { 32 };
    let owner: Pk = d.get(o..o + 32)?.try_into().ok()?;
    let amt = u64::from_le_bytes(d.get(o + 32..o + 40)?.try_into().ok()?);
    Some((owner, amt))
}

/// getProgramAccounts' params: every token account of `mint` (memcmp at 0; SPL Token accounts are exactly 165 bytes, Token-2022's
/// may be longer: no size filter), owner + amount only, the read slot
pub fn gpa_params(mint: &Pk, t22: bool) -> serde_json::Value {
    let prog = if t22 { &*pda::TOKEN_2022 } else { &*pda::TOKEN_PROGRAM };
    let mut f = vec![serde_json::json!({"memcmp": {"offset": 0, "bytes": b58(mint)}})];
    if !t22 { f.insert(0, serde_json::json!({"dataSize": 165})); }
    serde_json::json!([b58(prog), {"encoding": "base64", "commitment": "processed", "withContext": true, "dataSlice": {"offset": 32, "length": 40}, "filters": f}])
}

/// its answer (withContext): (context slot, (owner, amount) per account)
pub fn gpa_parse(v: &serde_json::Value) -> std::result::Result<(u64, Vec<(Pk, u64)>), String> {
    let slot = v["context"]["slot"].as_u64().ok_or("no context slot")?;
    let list = v["value"].as_array().ok_or("no value list")?;
    let mut out = Vec::with_capacity(list.len());
    for a in list {
        let s = a["account"]["data"][0].as_str().ok_or("no account data")?;
        let d = base64::engine::general_purpose::STANDARD.decode(s).map_err(|e| format!("base64: {e}"))?;
        out.push(acct_parse(&d, true).ok_or("short account data")?);
    }
    Ok((slot, out))
}

/// the read: the launch's program first, the other one when it has no account of the mint; FAM_TIMEOUT in all
pub async fn fam_read(rpc: &rpc::Rpc, mint: &Pk, t22: bool) -> (&'static str, std::result::Result<(u64, Vec<(Pk, u64)>), String>) {
    let one = |t: bool| async move {
        let b = rpc::Bounds::fetch(FAM_TIMEOUT, 1);
        match rpc.call_bounded("getProgramAccounts", gpa_params(mint, t), b).await { Ok(f) => gpa_parse(&f.value), Err(e) => Err(rpc::scrub(&e.msg)) }
    };
    let name = |t: bool| if t { "t22" } else { "spl" };
    let run = async {
        match one(t22).await {
            Ok((s, v)) if v.is_empty() => match one(!t22).await { Ok((s2, v2)) if !v2.is_empty() => (name(!t22), Ok((s2, v2))), _ => (name(t22), Ok((s, v))) },
            r => (name(t22), r),
        }
    };
    match tokio::time::timeout(FAM_TIMEOUT, run).await { Ok(r) => r, Err(_) => (name(t22), Err(format!("timeout {} ms", FAM_TIMEOUT.as_millis()))) }
}

/// the classification: `hold` = (owner, amount) per token account (an owner's accounts summed); `arm` / `now` = the on-curve books at
/// the arm and at the answer; the curve's and our holdings out
pub fn fam_classify(hold: &[(Pk, u64)], arm: &[(Pk, i64, bool)], now: &[(Pk, i64, bool)], curve: &Pk, user: &Pk) -> Fam {
    let mut bal: FxHashMap<Pk, i64> = FxHashMap::default();
    for (o, a) in hold { if o != curve && o != user { *bal.entry(*o).or_default() += (*a).min(i64::MAX as u64) as i64; } }
    let mut net: FxHashMap<Pk, (i64, bool)> = FxHashMap::default();
    for (w, n, cs) in arm.iter().chain(now.iter()) {
        let e = net.entry(*w).or_insert((i64::MIN, false));
        e.0 = e.0.max(*n);
        e.1 |= *cs;
    }
    let mut f = Fam::default();
    let (mut fam, mut cs_t, mut rv_t) = (0i64, 0i64, 0i64);
    for (o, b) in &bal {
        if *b <= 0 { continue; }
        f.n_holders += 1;
        let (n, cs) = net.get(o).copied().unwrap_or((0, false));
        let recv = *b > n.max(0) + FAM_TOL;
        if cs { cs_t += b; }
        if recv && *b >= FAM_MINH { f.recv_n += 1; rv_t += b; }
        if cs || recv { fam += b; }
    }
    let p = |x: i64| x as f64 / pl::SUPPLY * 100.0;
    (f.fam, f.cs_pct, f.recv_pct) = (p(fam), p(cs_t), p(rv_t));
    f
}

/// the probe's dip35 log state (rpc None and every count 0 with the flag off)
#[derive(Default)]
pub struct L35 { pub rpc: Option<Arc<rpc::Rpc>>, pub inflight: Arc<AtomicU64>, pub spawned: u64, pub reads: u64, pub hits: u64, pub busy: u64, pub errs: u64, pub lags: Vec<f64> }

impl L35 {
    /// the read client (only with the flag on): --presend-live-fam-rpc URL (`${VAR}` expanded from the environment) or the engine's
    /// rpc_url; its own endpoint name "fam" (its own rate bucket, never the exit path's)
    pub fn new(cfg: &Cfg) -> Result<L35> {
        if !cfg.fam_log { return Ok(L35::default()); }
        let url = match &cfg.fam_rpc {
            Some(u) => config::expand(u).with_context(|| "--presend-live-fam-rpc names an env var that is empty / missing")?,
            None => PRIMARY_URL.get().cloned().context("--presend-live-fam-log: no rpc_url (give --presend-live-fam-rpc URL)")?,
        };
        Ok(L35 { rpc: Some(Arc::new(rpc::Rpc::race(vec![rpc::Endpoint { name: "fam".into(), url, bearer: None }]))), ..Default::default() })
    }
}

impl PsLive {
    /// dip35 (--presend-live-fam-log): a presend_live_arm (T2 or re-arm) asks for the holders read (nothing without the flag; busy: skipped)
    pub(super) fn fam_arm(&mut self, w: u64, mint: Pk, rearm: bool, arm_slot: u64) {
        // dip43c: the book's top-holder snapshot on the primary rpc (nothing unless --presend-live-tbal-src largest)
        self.largest_arm(w, mint);
        if !self.cfg.fam_log { return; }
        if self.l35.inflight.load(Ordering::SeqCst) >= FAM_INFLIGHT {
            self.l35.busy += 1;
            self.rec(serde_json::json!({"ev": "presend_live_fam", "w": w, "mint": b58(&mint), "rearm": rearm, "arm_slot": arm_slot, "hit": null, "err": "busy"}));
            return;
        }
        let (t22, curve) = self.launches.get(&mint).map_or((true, [0u8; 32]), |l| (l.is_create_v2, l.bonding_curve));
        let req = FamReq { w, mint, rearm, arm_slot, t22, curve, at: Instant::now(), book: self.det.fam_book(&mint) };
        self.l35.spawned += 1;
        self.exec(Cmd::Fam(Box::new(req)));
    }

    /// dip35: the read's answer -> the presend_live_fam record (the classification against the arm's and today's books)
    pub(super) fn fam_done(&mut self, r: FamRes) {
        let q = &r.req;
        let lag = q.at.elapsed().as_secs_f64() * 1e3;
        let mut rec = serde_json::json!({"ev": "presend_live_fam", "w": q.w, "mint": b58(&q.mint), "rearm": q.rearm, "arm_slot": q.arm_slot, "lag_ms": (lag * 10.0).round() / 10.0,
            "thr": self.cfg.fam_thr, "prog": r.prog});
        match &r.read {
            Err(e) => {
                self.l35.errs += 1;
                rec["hit"] = serde_json::Value::Null;
                rec["err"] = e.clone().into();
            }
            Ok((slot, hold)) => {
                let now = self.det.fam_book(&q.mint);
                let hist = if q.book.is_some() && now.is_some() { "full" } else { "partial" };
                let f = fam_classify(hold, q.book.as_deref().unwrap_or(&[]), now.as_deref().unwrap_or(&[]), &q.curve, &self.user);
                let hit = f.fam >= self.cfg.fam_thr;
                self.l35.reads += 1;
                if hit { self.l35.hits += 1; }
                if self.l35.lags.len() < LAG_KEEP { self.l35.lags.push(lag); }
                let r2 = |x: f64| (x * 100.0).round() / 100.0;
                for (k, v) in [("fam", r2(f.fam)), ("cs_pct", r2(f.cs_pct)), ("recv_pct", r2(f.recv_pct))] { rec[k] = v.into(); }
                rec["recv_n"] = f.recv_n.into();
                // dip43 A3 / A4 (nothing with --presend-live-tbal / --presend-live-fanout off): the snapshot into the true-balance book, the fan-out verdict
                if let Some(j) = self.fam43(q, *slot, hold, f.recv_n) { rec["fanout"] = j; }
                rec["n_holders"] = f.n_holders.into();
                rec["hist"] = hist.into();
                rec["read_slot"] = (*slot).into();
                rec["hit"] = hit.into();
                rec["err"] = serde_json::Value::Null;
                if hit {
                    self.line(format!("  PRESEND LIVE FAM (log) w{} {} fam {:.1}% (cs {:.1}%, recv {} / {:.1}%){} -> would skip", q.w, b58(&q.mint), f.fam, f.cs_pct, f.recv_n, f.recv_pct,
                        if hist == "partial" { " [partial history]" } else { "" }));
                }
            }
        }
        self.rec(rec);
    }

    /// dip35: the run_end summary (None with the flag off)
    pub(super) fn l35_json(&self) -> Option<serde_json::Value> {
        if !self.cfg.fam_log { return None; }
        let mut v = self.l35.lags.clone();
        v.sort_by(|a, b| a.total_cmp(b));
        let p50 = (!v.is_empty()).then(|| (v[v.len() / 2] * 10.0).round() / 10.0);
        Some(serde_json::json!({"fam": {"thr": self.cfg.fam_thr, "asked": self.l35.spawned, "reads": self.l35.reads, "hits": self.l35.hits, "busy": self.l35.busy,
            "errors": self.l35.errs, "lag_ms_p50": p50}}))
    }
}
