//! M2 dip detector (ops/strategies/dipdetect/PORT.md, 2026-10-25 PKT): a 3-seed GBDT on 25 features that predicts what OUR
//! buy would make on a dump (the study replay: 35 ms landing, 0.55 SOL, +5% guard, sell 4 slots after the entry slot, all
//! costs), trained on day R2 only (ops/strategies/dipdetect/dd5_model.py variant `v3_reg4_top25`). Stage A = today's watch
//! envelope + "M2 score >= threshold" instead of the IMIT1 gate.
//!
//! The features are the study's, computed per token INCREMENTALLY from the executed feed's real trades (O(1) amortised per
//! trade; the dump-time work is O(80) for coh_20 plus the GBDT):
//!   * 13 day-array features (ops/strategies/patterns/p1_build.py) AT the trade, i.e. INCLUDING it: move, age, curve,
//!     from_bun, ret30, ns1, ns3, net3, dd3, maxb30, nwal, nbot_hold, fam_hold
//!   * 12 dump extras (ops/strategies/dipdetect/dd1_build.py `work`), from the state BEFORE the trade: since_buy_s, s_buy,
//!     s_hold, coh_n, coh_sol, coh_20, bundle_sol, sold_slot_sol, pro_after_prev, drop_pct (of the trade itself), uniq_b,
//!     since_dump2_s
//! Every value is computed in f64 in the Python's operation order and rounded to f32 (the study's arrays are float32); the
//! bins compare that f32 value (widened) with the f64 edges, as numpy's searchsorted does.
//! Trades: chain order (slot, tx index, event index); synthetic gap trades of the IMIT1 book are NOT fed (the study's day
//! arrays have none). Arrival times are the replay's block-position clock with the block size unknown (400), as the live
//! engine (`dip_imit::arr` with no block sizes) and the study's R3 / R4 arrays. Wallets are compared by their 32 bytes (the
//! study keyed them by crc32 of the base58 text: a collision there is ~1e-7 per wallet and is not reproduced).
//! Parity with the Python: `cargo test --release --lib dip_model` (testdata/dip_m2_parity.json from
//! ops/strategies/dipdetect/dd22_m2_parity.py).
use crate::dip_imit::T;
use crate::tx::Pk;
use rustc_hash::{FxHashMap, FxHashSet};
use serde_json::Value;
use std::collections::VecDeque;

/// the model's feature order (checked against the bundle's `fn` at load)
pub const FN: [&str; 25] = ["move", "age", "curve", "from_bun", "ret30", "ns1", "ns3", "net3", "dd3", "maxb30", "nwal", "nbot_hold", "fam_hold",
    "since_buy_s", "s_buy", "s_hold", "coh_n", "coh_sol", "coh_20", "bundle_sol", "sold_slot_sol", "pro_after_prev", "drop_pct", "uniq_b", "since_dump2_s"];
pub const NF: usize = 25;
const SMS: f64 = 212.0;
const BIG_SELL: u64 = 1_000_000_000;
const COH20_TRADES: usize = 80;
const COH20_SLOTS: u64 = 20;
const PRO_AFTER_MS: f64 = 1000.0;

/// numpy's float32 storage of a float64 value, widened back (what the study's bins saw)
#[inline]
fn f32r(x: f64) -> f64 { x as f32 as f64 }

/// the replay's arrival clock (p1_build.arrival with no block size table): slot x 212 ms + index / max(400, index + 1) x 212 ms
#[inline]
pub fn arrival(s: u64, i: u32) -> f64 {
    let size = 400u64.max(i as u64 + 1);
    s as f64 * SMS + (i as f64 / size as f64) * SMS
}

/// one real (non-synthetic) curve trade, as the M2 state needs it
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Tr { pub s: u64, pub i: u32, pub j: i32, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64, pub user: Pk }

impl Tr {
    /// from the IMIT1 book's trade (base58 user); None for synthetic gap trades or an undecodable user
    pub fn from_t(t: &T) -> Option<Tr> {
        if t.syn { return None; }
        let u: Pk = bs58::decode(&t.user).into_vec().ok()?.try_into().ok()?;
        Some(Tr { s: t.s, i: t.i, j: t.j, buy: t.buy, sol: t.sol, tok: t.tok, vsol: t.vsol, vtok: t.vtok, user: u })
    }
    #[inline]
    fn key(&self) -> (u64, u32, i32) { (self.s, self.i, self.j) }
}

// ---------------------------------------------------------------------------------------------------------------------
// the bundle: model + wallet sets (one file, --dip-m2)
// ---------------------------------------------------------------------------------------------------------------------

/// the wallet sets the features use: the TRAIN-hours cohort (coh_*), cohort + the 3 IMIT1 wallets ("pro": pro_after_prev),
/// the R2 bot list (bot id, family = label "F..."; nbot_hold / fam_hold)
pub struct Sets { pub cohort: FxHashSet<Pk>, pub upro: FxHashSet<Pk>, pub bots: FxHashMap<Pk, (u16, bool)> }

/// what a wallet is to the features (looked up once per wallet per token)
#[derive(Clone, Copy, Debug, Default)]
struct WKind { coh: bool, pro: bool, bot: u16, fam: bool }

impl Sets {
    #[inline]
    fn kind(&self, u: &Pk) -> WKind {
        let (bot, fam) = self.bots.get(u).copied().unwrap_or((0, false));
        WKind { coh: self.cohort.contains(u), pro: self.upro.contains(u), bot, fam }
    }
}

/// one seed's trees, flattened (node arrays; a leaf has f = -1)
struct Seed { f0: f64, lr: f64, roots: Vec<u32>, f: Vec<i16>, b: Vec<i16>, l: Vec<u32>, r: Vec<u32>, w: Vec<f64> }

/// the GBDT: per-feature bin edges + the seeds; score = mean of the seeds' predictions (dd5_model: np.mean over the seeds)
pub struct Model { pub name: String, edges: Vec<Vec<f64>>, seeds: Vec<Seed> }

/// floats are strings in the bundle (exact: Rust's parser is correctly rounded); plain JSON numbers are accepted too
fn num(v: &Value) -> Result<f64, String> {
    match v {
        Value::String(s) => s.parse::<f64>().map_err(|e| format!("bad float {s}: {e}")),
        Value::Number(n) => n.as_f64().ok_or_else(|| format!("bad number {n}")),
        _ => Err(format!("not a number: {v}")),
    }
}
fn ints(v: &Value, what: &str) -> Result<Vec<i64>, String> {
    v.as_array().ok_or_else(|| format!("no {what}"))?.iter().map(|x| x.as_i64().ok_or_else(|| format!("bad {what}"))).collect()
}

impl Model {
    pub fn n_trees(&self) -> usize { self.seeds.iter().map(|s| s.roots.len()).sum() }
    pub fn n_nodes(&self) -> usize { self.seeds.iter().map(|s| s.f.len()).sum() }
    pub fn n_seeds(&self) -> usize { self.seeds.len() }

    /// dd_gbdt.binize: searchsorted(edges, x, side="right") + 1; non-finite -> 0
    #[inline]
    pub fn bins(&self, x: &[f64; NF]) -> [i16; NF] {
        let mut b = [0i16; NF];
        for (k, (&v, e)) in x.iter().zip(self.edges.iter()).enumerate() {
            b[k] = if v.is_finite() { e.partition_point(|&q| q <= v) as i16 + 1 } else { 0 };
        }
        b
    }

    /// SHRED FIRE (dip14): (lowest, highest) score when feature k may be anywhere in [lo[k], hi[k]] (each on its own: sound and
    /// conservative); a split whose bin range straddles its threshold follows both branches. lo == hi gives exactly `score`
    /// (the same sums in the same order)
    pub fn score_bounds(&self, lo: &[f64; NF], hi: &[f64; NF]) -> (f64, f64) {
        let (bl, bh) = (self.bins(lo), self.bins(hi));
        let br: [(i16, i16); NF] = std::array::from_fn(|k| (bl[k].min(bh[k]), bl[k].max(bh[k])));
        fn walk(sd: &Seed, n: usize, br: &[(i16, i16); NF]) -> (f64, f64) {
            let f = sd.f[n];
            if f < 0 { return (sd.w[n], sd.w[n]); }
            let (a, z) = br[f as usize];
            let b = sd.b[n];
            if z <= b { walk(sd, sd.l[n] as usize, br) }
            else if a > b { walk(sd, sd.r[n] as usize, br) }
            else { let (p, q) = (walk(sd, sd.l[n] as usize, br), walk(sd, sd.r[n] as usize, br)); (p.0.min(q.0), p.1.max(q.1)) }
        }
        let (mut amin, mut amax) = (0.0f64, 0.0f64);
        for (k, sd) in self.seeds.iter().enumerate() {
            let (mut pmin, mut pmax) = (sd.f0, sd.f0);
            for &root in &sd.roots { let (a, b) = walk(sd, root as usize, &br); pmin += sd.lr * a; pmax += sd.lr * b; }
            if k == 0 { amin = pmin; amax = pmax; } else { amin += pmin; amax += pmax; }
        }
        (amin / self.seeds.len() as f64, amax / self.seeds.len() as f64)
    }

    /// the predicted SOL per attempt: per seed F0 + lr x leaf weight, tree by tree (numpy's order); seeds averaged as np.mean
    /// over axis 0 ((p0 + p1) + p2) / 3
    pub fn score(&self, x: &[f64; NF]) -> f64 {
        let bins = self.bins(x);
        let mut acc = 0.0f64;
        for (k, sd) in self.seeds.iter().enumerate() {
            let mut p = sd.f0;
            for &root in &sd.roots {
                let mut n = root as usize;
                loop {
                    let f = sd.f[n];
                    if f < 0 { break; }
                    n = if bins[f as usize] <= sd.b[n] { sd.l[n] } else { sd.r[n] } as usize;
                }
                p += sd.lr * sd.w[n];
            }
            acc = if k == 0 { p } else { acc + p };
        }
        acc / self.seeds.len() as f64
    }
}

/// the deployable bundle (ops/strategies/dipdetect/dd21_m2_bundle.py)
pub struct Bundle { pub model: Model, pub sets: Sets, pub thr_default: f64, pub sha256: String, pub path: String, pub n_t3: usize, pub n_family: usize, pub built: String }

impl Bundle {
    pub fn load(path: &str) -> Result<Bundle, String> {
        use sha2::Digest;
        let raw = std::fs::read(path).map_err(|e| format!("{path}: {e}"))?;
        let sha = sha2::Sha256::digest(&raw).iter().map(|b| format!("{b:02x}")).collect::<String>();
        let v: Value = serde_json::from_slice(&raw).map_err(|e| format!("{path}: {e}"))?;
        if v["kind"].as_str() != Some("dip_m2_bundle") { return Err(format!("{path}: not a dip_m2_bundle")); }
        if v["format"].as_i64() != Some(1) { return Err(format!("{path}: bundle format {} (this engine reads 1)", v["format"])); }
        let fns: Vec<&str> = v["fn"].as_array().ok_or("no fn")?.iter().map(|x| x.as_str().unwrap_or("")).collect();
        if fns != FN { return Err(format!("{path}: feature order {fns:?} differs from dip_model::FN")); }
        if v["combine"].as_str() != Some("mean") { return Err(format!("{path}: combine {} (mean expected)", v["combine"])); }
        let edges: Vec<Vec<f64>> = v["edges"].as_array().ok_or("no edges")?.iter()
            .map(|e| e.as_array().ok_or_else(|| "bad edges".to_string())?.iter().map(num).collect::<Result<Vec<f64>, String>>()).collect::<Result<_, _>>()?;
        if edges.len() != NF { return Err(format!("{path}: {} edge lists", edges.len())); }
        if edges.iter().any(|e| e.windows(2).any(|w| w[0] >= w[1]) || e.iter().any(|x| !x.is_finite())) { return Err(format!("{path}: edges not strictly increasing")); }
        let mut seeds = Vec::new();
        for s in v["seeds"].as_array().ok_or("no seeds")? {
            let (f, b, l, r) = (ints(&s["f"], "f")?, ints(&s["b"], "b")?, ints(&s["l"], "l")?, ints(&s["r"], "r")?);
            let w: Vec<f64> = s["w"].as_array().ok_or("no w")?.iter().map(num).collect::<Result<_, _>>()?;
            let roots = ints(&s["roots"], "roots")?;
            let n = f.len();
            if [b.len(), l.len(), r.len(), w.len()].iter().any(|&x| x != n) { return Err(format!("{path}: node arrays of unequal length")); }
            for k in 0..n {
                if f[k] >= 0 {
                    if f[k] as usize >= NF || l[k] < 0 || r[k] < 0 || l[k] as usize >= n || r[k] as usize >= n || l[k] as usize <= k || r[k] as usize <= k {
                        return Err(format!("{path}: bad split node {k}"));
                    }
                    if b[k] < 0 || b[k] > 64 { return Err(format!("{path}: bad bin {}", b[k])); }
                } else if !w[k].is_finite() { return Err(format!("{path}: bad leaf {k}")); }
            }
            if roots.iter().any(|&x| x < 0 || x as usize >= n) { return Err(format!("{path}: bad root")); }
            seeds.push(Seed { f0: num(&s["F0"])?, lr: num(&s["lr"])?, roots: roots.iter().map(|&x| x as u32).collect(), f: f.iter().map(|&x| x as i16).collect(),
                              b: b.iter().map(|&x| x as i16).collect(), l: l.iter().map(|&x| x.max(0) as u32).collect(), r: r.iter().map(|&x| x.max(0) as u32).collect(), w });
        }
        if seeds.is_empty() { return Err(format!("{path}: no seeds")); }
        let pk = |x: &Value| -> Result<Pk, String> {
            let s = x.as_str().ok_or("wallet not a string")?;
            bs58::decode(s).into_vec().ok().and_then(|b| <Pk>::try_from(b).ok()).ok_or_else(|| format!("bad wallet {s}"))
        };
        let cohort: FxHashSet<Pk> = v["cohort"].as_array().ok_or("no cohort")?.iter().map(pk).collect::<Result<_, _>>()?;
        let t3: Vec<Pk> = v["t3"].as_array().ok_or("no t3")?.iter().map(pk).collect::<Result<_, _>>()?;
        let mut upro = cohort.clone();
        upro.extend(t3.iter().copied());
        let mut bots: FxHashMap<Pk, (u16, bool)> = FxHashMap::default();
        for (u, x) in v["bots"].as_object().ok_or("no bots")? {
            let id = x[0].as_u64().ok_or("bad bot id")?;
            if id == 0 || id > u16::MAX as u64 { return Err(format!("{path}: bot id {id} out of range")); }
            bots.insert(pk(&Value::String(u.clone()))?, (id as u16, x[1].as_str().unwrap_or("").starts_with('F')));
        }
        let n_family = bots.values().filter(|x| x.1).count();
        Ok(Bundle { model: Model { name: v["name"].as_str().unwrap_or("?").to_string(), edges, seeds }, thr_default: num(&v["thr_default"])?,
                    sets: Sets { cohort, upro, bots }, sha256: sha, path: path.to_string(), n_t3: t3.len(), n_family,
                    built: v["built"].as_str().unwrap_or("?").to_string() })
    }

    /// one line for the start log
    pub fn summary(&self) -> String {
        format!("model {} ({} seeds, {} trees, {} nodes, {} features) | cohort {} | IMIT1 wallets {} | bots {} (family {}) | default threshold {} | built {} | sha256 {}",
            self.model.name, self.model.n_seeds(), self.model.n_trees(), self.model.n_nodes(), NF, self.sets.cohort.len(), self.n_t3, self.sets.bots.len(), self.n_family,
            self.thr_default, self.built, self.sha256)
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// per-token state
// ---------------------------------------------------------------------------------------------------------------------

/// one applied trade (chain order)
#[derive(Clone, Copy, Debug)]
struct Rec { s: u64, i: u32, j: i32, buy: bool, sol: u64, tok: u64, vsol: u64, vtok: u64, w: u32, arr: f64, pp: f64, pm: f64, ppre: f64 }

/// a wallet's order-dependent state on this token (dd1_build `W[u]` + the seen / bought / cohort-bought sets)
#[derive(Clone, Copy, Debug, Default)]
struct WSt { seen: bool, bought: bool, buy_sol: u64, nb: u32, first_buy_s: u64 }

/// why a dump could not be scored
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Skip { NoTrades, NotSell }
impl Skip { pub fn as_str(&self) -> &'static str { match self { Skip::NoTrades => "no_trades", Skip::NotSell => "not_sell" } } }

/// M2 state of one token, from its create on (the engine makes it at the create event, as the IMIT1 book)
pub struct Tok {
    s0: u64,
    recs: Vec<Rec>,
    users: Vec<(Pk, WKind)>,
    uidx: FxHashMap<Pk, u32>,
    // ---- order-dependent (reset + replayed by `rebuild` after an out-of-order trade) ----
    ws: Vec<WSt>,
    nwal: u32, uniq_b: u32, coh_n: u32, coh_sol: u64, bundle_sol: u64,
    p_bun: Option<f64>,
    c_sell: Vec<u32>, c_bsol: Vec<u64>, c_ssol: Vec<u64>,
    slot_cur: Option<u64>, slot_start: usize, ssol_slot: u64, pre_ssol_slot: u64,
    lo3: usize, lo30: usize, p30: usize,
    dq3: VecDeque<usize>, dq30: VecDeque<usize>,
    last_buy: Option<f64>, big_arr: Option<f64>, last2: Option<f64>, pre_last2: Option<f64>,
    pro_after: u32,
    bpos: FxHashMap<u16, (f64, f64)>, nhold: i32, fhold: i32,
    /// an out-of-order trade was inserted: the state is replayed (in chain order) before the next features
    dirty: bool,
    /// pre-state of a trade != post-state of the trade before it (a trade the feed missed), duplicates ignored, out-of-order
    /// inserts
    pub gaps: u32, pub dups: u32, pub reorders: u32,
}

/// SHRED FIRE (dip14): the M2 features that depend on the dump's tx index (its arrival on the block-position clock): since_buy_s
/// and since_dump2_s (FN 13, 24); both non-decreasing in the index
pub const TIME_FEATS: [usize; 2] = [13, 24];

/// SHRED FIRE (dip14): a token's M2 state before a speculative push of its NEWEST trade (`Tok::push_spec`); `rollback` restores it
/// exactly: the appended record, a new wallet, the wallet's / its bot's entries the update touched, every scalar and window
#[derive(Clone, Debug)]
pub struct TokCkpt {
    n_recs: usize, n_users: usize, ws_w: Option<(usize, WSt)>, bpos_e: Option<(u16, Option<(f64, f64)>)>,
    nwal: u32, uniq_b: u32, coh_n: u32, coh_sol: u64, bundle_sol: u64, p_bun: Option<f64>, n_c: usize,
    slot_cur: Option<u64>, slot_start: usize, ssol_slot: u64, pre_ssol_slot: u64, lo3: usize, lo30: usize, p30: usize,
    dq3: VecDeque<usize>, dq30: VecDeque<usize>,
    last_buy: Option<f64>, big_arr: Option<f64>, last2: Option<f64>, pre_last2: Option<f64>, pro_after: u32, nhold: i32, fhold: i32,
    dirty: bool, gaps: u32, dups: u32, reorders: u32,
}

impl Tok {
    /// SHRED FIRE (dip14): replay the state now if an out-of-order trade made it stale (as `features` would)
    pub fn clean(&mut self) { if self.dirty { self.rebuild(); } }

    /// SHRED FIRE (dip14): push `t` speculatively; None (nothing changed) unless it is strictly newer than every applied trade.
    /// The state is cleaned first (a replay after an out-of-order trade), so the push is applied at once and is undone exactly
    pub fn push_spec(&mut self, t: &Tr, sets: &Sets) -> Option<TokCkpt> {
        self.clean();
        if self.recs.last().is_some_and(|r| (r.s, r.i, r.j) >= t.key()) { return None; }
        let w_opt = self.uidx.get(&t.user).copied();
        let kind = match w_opt { Some(w) => self.users[w as usize].1, None => sets.kind(&t.user) };
        let ck = TokCkpt {
            n_recs: self.recs.len(), n_users: self.users.len(), ws_w: w_opt.map(|w| (w as usize, self.ws[w as usize])),
            bpos_e: (kind.bot != 0).then(|| (kind.bot, self.bpos.get(&kind.bot).copied())),
            nwal: self.nwal, uniq_b: self.uniq_b, coh_n: self.coh_n, coh_sol: self.coh_sol, bundle_sol: self.bundle_sol, p_bun: self.p_bun, n_c: self.c_sell.len(),
            slot_cur: self.slot_cur, slot_start: self.slot_start, ssol_slot: self.ssol_slot, pre_ssol_slot: self.pre_ssol_slot, lo3: self.lo3, lo30: self.lo30,
            p30: self.p30, dq3: self.dq3.clone(), dq30: self.dq30.clone(), last_buy: self.last_buy, big_arr: self.big_arr, last2: self.last2,
            pre_last2: self.pre_last2, pro_after: self.pro_after, nhold: self.nhold, fhold: self.fhold, dirty: self.dirty, gaps: self.gaps, dups: self.dups,
            reorders: self.reorders,
        };
        self.push(t, sets);
        Some(ck)
    }

    /// SHRED FIRE (dip14): undo a `push_spec`
    pub fn rollback(&mut self, c: TokCkpt) {
        self.recs.truncate(c.n_recs);
        for (u, _) in self.users.drain(c.n_users..) { self.uidx.remove(&u); }
        self.ws.truncate(c.n_users);
        if let Some((w, st)) = c.ws_w { self.ws[w] = st; }
        if let Some((bot, old)) = c.bpos_e { match old { Some(v) => { self.bpos.insert(bot, v); } None => { self.bpos.remove(&bot); } } }
        self.c_sell.truncate(c.n_c); self.c_bsol.truncate(c.n_c); self.c_ssol.truncate(c.n_c);
        self.nwal = c.nwal; self.uniq_b = c.uniq_b; self.coh_n = c.coh_n; self.coh_sol = c.coh_sol; self.bundle_sol = c.bundle_sol; self.p_bun = c.p_bun;
        self.slot_cur = c.slot_cur; self.slot_start = c.slot_start; self.ssol_slot = c.ssol_slot; self.pre_ssol_slot = c.pre_ssol_slot;
        self.lo3 = c.lo3; self.lo30 = c.lo30; self.p30 = c.p30; self.dq3 = c.dq3; self.dq30 = c.dq30;
        self.last_buy = c.last_buy; self.big_arr = c.big_arr; self.last2 = c.last2; self.pre_last2 = c.pre_last2; self.pro_after = c.pro_after;
        self.nhold = c.nhold; self.fhold = c.fhold; self.dirty = c.dirty; self.gaps = c.gaps; self.dups = c.dups; self.reorders = c.reorders;
    }

    /// SHRED FIRE (dip14): since_buy_s and since_dump2_s of the NEWEST trade (a sell, as `features`) if its arrival time on the
    /// block-position clock were `arr` (f32-rounded as the features)
    pub fn time_feats_at(&self, arr: f64) -> (f64, f64) {
        let since_buy = self.last_buy.map(|b| (arr - b) / 1000.0).unwrap_or(1e9);
        let since2 = self.pre_last2.map(|b| (arr - b) / 1000.0).unwrap_or(1e9);
        (f32r(since_buy), f32r(since2))
    }

    pub fn new(create_slot: u64) -> Tok {
        Tok { s0: create_slot, recs: Vec::new(), users: Vec::new(), uidx: FxHashMap::default(), ws: Vec::new(), nwal: 0, uniq_b: 0, coh_n: 0, coh_sol: 0, bundle_sol: 0,
              p_bun: None, c_sell: vec![0], c_bsol: vec![0], c_ssol: vec![0], slot_cur: None, slot_start: 0, ssol_slot: 0, pre_ssol_slot: 0, lo3: 0, lo30: 0, p30: 0,
              dq3: VecDeque::new(), dq30: VecDeque::new(), last_buy: None, big_arr: None, last2: None, pre_last2: None, pro_after: 0, bpos: FxHashMap::default(),
              nhold: 0, fhold: 0, dirty: false, gaps: 0, dups: 0, reorders: 0 }
    }
    pub fn n(&self) -> usize { self.recs.len() }
    pub fn create_slot(&self) -> u64 { self.s0 }
    /// the newest applied trade's chain key (slot, tx index, event index)
    pub fn last_key(&self) -> Option<(u64, u32, i32)> { self.recs.last().map(|r| (r.s, r.i, r.j)) }

    fn rec(&mut self, t: &Tr, sets: &Sets) -> Rec {
        let w = match self.uidx.get(&t.user) {
            Some(&w) => w,
            None => { let w = self.users.len() as u32; self.users.push((t.user, sets.kind(&t.user))); self.uidx.insert(t.user, w); self.ws.push(WSt::default()); w }
        };
        // p1_build: ppost = V / T; ppre = Vpre / max(Tpre, 1) where Tpre > 0, else ppost
        let (v, tk) = (t.vsol as f64, t.vtok as f64);
        let (vp, tp) = if t.buy { (v - t.sol as f64, tk + t.tok as f64) } else { (v + t.sol as f64, tk - t.tok as f64) };
        let pp = v / tk;
        let ppre = if tp > 0.0 { vp / tp.max(1.0) } else { pp };
        Rec { s: t.s, i: t.i, j: t.j, buy: t.buy, sol: t.sol, tok: t.tok, vsol: t.vsol, vtok: t.vtok, w, arr: arrival(t.s, t.i), pp, pm: if pp >= ppre { pp } else { ppre }, ppre }
    }

    /// add one real trade (any order; duplicates ignored). In chain order the update is O(1) amortised; a trade older than the
    /// newest one is inserted in place and marks the state for a replay, done lazily by the next `features` (rare).
    pub fn push(&mut self, t: &Tr, sets: &Sets) {
        let key = t.key();
        if let Some(last) = self.recs.last() {
            let lk = (last.s, last.i, last.j);
            if key == lk { self.dups += 1; return; }
            if key < lk {
                let pos = self.recs.partition_point(|r| (r.s, r.i, r.j) < key);
                if self.recs.get(pos).is_some_and(|r| (r.s, r.i, r.j) == key) { self.dups += 1; return; }
                let r = self.rec(t, sets);
                self.recs.insert(pos, r);
                self.reorders += 1;
                self.dirty = true;
                return;
            }
            // a trade the feed missed between the two: the pre-state differs from the last post-state
            let pre = if t.buy { (t.vsol.wrapping_sub(t.sol), t.vtok.wrapping_add(t.tok)) } else { (t.vsol.wrapping_add(t.sol), t.vtok.wrapping_sub(t.tok)) };
            if pre != (last.vsol, last.vtok) { self.gaps += 1; }
        }
        let r = self.rec(t, sets);
        self.recs.push(r);
        if !self.dirty { self.apply(self.recs.len() - 1); }
    }

    /// replay every applied trade in chain order (after an out-of-order insert)
    fn rebuild(&mut self) {
        for w in self.ws.iter_mut() { *w = WSt::default(); }
        self.nwal = 0; self.uniq_b = 0; self.coh_n = 0; self.coh_sol = 0; self.bundle_sol = 0; self.p_bun = None;
        self.c_sell.clear(); self.c_sell.push(0); self.c_bsol.clear(); self.c_bsol.push(0); self.c_ssol.clear(); self.c_ssol.push(0);
        self.slot_cur = None; self.slot_start = 0; self.ssol_slot = 0; self.pre_ssol_slot = 0; self.lo3 = 0; self.lo30 = 0; self.p30 = 0;
        self.dq3.clear(); self.dq30.clear(); self.last_buy = None; self.big_arr = None; self.last2 = None; self.pre_last2 = None; self.pro_after = 0;
        self.bpos.clear(); self.nhold = 0; self.fhold = 0;
        self.gaps = 0; self.dirty = false;
        for k in 0..self.recs.len() {
            if k > 0 {
                let (t, p) = (&self.recs[k], &self.recs[k - 1]);
                let pre = if t.buy { (t.vsol.wrapping_sub(t.sol), t.vtok.wrapping_add(t.tok)) } else { (t.vsol.wrapping_add(t.sol), t.vtok.wrapping_sub(t.tok)) };
                if pre != (p.vsol, p.vtok) { self.gaps += 1; }
            }
            self.apply(k);
        }
    }

    /// the state update with recs[k] (recs[..k] applied before)
    fn apply(&mut self, k: usize) {
        let r = self.recs[k];
        let kind = self.users[r.w as usize].1;
        // slot change (dd1_build: per-slot sells reset at the first trade of a new slot)
        if self.slot_cur != Some(r.s) { self.slot_cur = Some(r.s); self.slot_start = k; self.ssol_slot = 0; }
        self.pre_ssol_slot = self.ssol_slot;
        self.pre_last2 = self.last2;
        // prefix sums (p1_build cumsum: sells count, buy SOL, sell SOL)
        let (cs, cb, cx) = (*self.c_sell.last().unwrap(), *self.c_bsol.last().unwrap(), *self.c_ssol.last().unwrap());
        self.c_sell.push(cs + (!r.buy) as u32);
        self.c_bsol.push(cb + if r.buy { r.sol } else { 0 });
        self.c_ssol.push(cx + if r.buy { 0 } else { r.sol });
        // window pointers: first index with slot >= s - 2 (3-slot window) / s - 29 (30-slot window); trades with slot <= s - 30
        while self.recs[self.lo3].s + 2 < r.s { self.lo3 += 1; }
        while self.recs[self.lo30].s + 29 < r.s { self.lo30 += 1; }
        while self.p30 < k && self.recs[self.p30].s + 30 <= r.s { self.p30 += 1; }
        // dd3: max(ppost, ppre) over the 3-slot window (monotone deque)
        while self.dq3.back().is_some_and(|&b| self.recs[b].pm <= r.pm) { self.dq3.pop_back(); }
        self.dq3.push_back(k);
        while self.dq3.front().is_some_and(|&f| f < self.lo3) { self.dq3.pop_front(); }
        // maxb30: largest buy over the 30-slot window
        if r.buy {
            while self.dq30.back().is_some_and(|&b| self.recs[b].sol <= r.sol) { self.dq30.pop_back(); }
            self.dq30.push_back(k);
        }
        while self.dq30.front().is_some_and(|&f| f < self.lo30) { self.dq30.pop_front(); }
        // the create slot: bundle SOL (buys IN the create slot), the price after its last trade (p_bun)
        if r.s <= self.s0 { self.p_bun = Some(r.pp); }
        if r.buy && r.s == self.s0 { self.bundle_sol += r.sol; }
        // wallets (p1_build seen_u / dd1_build W, ub, cohb)
        let w = &mut self.ws[r.w as usize];
        if !w.seen { w.seen = true; self.nwal += 1; }
        if r.buy {
            w.buy_sol += r.sol; w.nb += 1;
            if w.nb == 1 { w.first_buy_s = r.s; }
            if !w.bought { w.bought = true; self.uniq_b += 1; if kind.coh { self.coh_n += 1; } }
            if kind.coh { self.coh_sol += r.sol; }
            if kind.pro && self.big_arr.is_some_and(|b| r.arr - b <= PRO_AFTER_MS) { self.pro_after += 1; }
            self.last_buy = Some(r.arr);
        } else {
            self.ssol_slot += r.sol;
            if r.sol >= BIG_SELL { self.big_arr = Some(r.arr); }
            let (v, t) = (r.vsol as f64, r.vtok as f64);
            if (1.0 - (v / t) / ((v + r.sol as f64) / (t - r.tok as f64))) * 100.0 >= 2.0 { self.last2 = Some(r.arr); }
        }
        // bots holding (p1_build: a bot holds while its position > 1% of its own peak position on this token)
        if kind.bot != 0 {
            let e = self.bpos.entry(kind.bot).or_insert((0.0, f64::NAN));
            let was = e.0 > 0.01 * if e.1.is_nan() { 1.0 } else { e.1 };
            e.0 += if r.buy { r.tok as f64 } else { -(r.tok as f64) };
            e.1 = if e.1.is_nan() { if 0.0 >= e.0 { 0.0 } else { e.0 } } else if e.1 >= e.0 { e.1 } else { e.0 };
            let now = e.0 > 0.01 * e.1;
            if now != was {
                let d = if now { 1 } else { -1 };
                self.nhold += d;
                if kind.fam { self.fhold += d; }
            }
        }
    }

    /// the 25 features (FN order) at the newest trade, which must be a sell (a dump); f32-rounded as the study's arrays.
    /// Replays the state first when an out-of-order trade came in since the last call.
    pub fn features(&mut self) -> Result<[f64; NF], Skip> {
        if self.dirty { self.rebuild(); }
        let k = self.recs.len().checked_sub(1).ok_or(Skip::NoTrades)?;
        let r = &self.recs[k];
        if r.buy { return Err(Skip::NotSell); }
        let ppre0 = self.recs[0].ppre;
        let pp = r.pp;
        // ---- p1_build (including the trade)
        let mv = (pp / r.ppre - 1.0) * 100.0;
        let age = r.s as f64 - self.s0 as f64;
        let curve = r.vsol as f64 / 1e9;
        let from_bun = pp / self.p_bun.unwrap_or(ppre0);
        let pw = if self.p30 > 0 { self.recs[self.p30 - 1].pp } else { ppre0 };
        let ret30 = (pp / pw - 1.0) * 100.0;
        let ns1 = (self.c_sell[k + 1] - self.c_sell[self.slot_start]) as f64;
        let ns3 = (self.c_sell[k + 1] - self.c_sell[self.lo3]) as f64;
        let net3 = (self.c_bsol[k + 1] - self.c_bsol[self.lo3]) as f64 / 1e9 - (self.c_ssol[k + 1] - self.c_ssol[self.lo3]) as f64 / 1e9;
        let pm = self.dq3.front().map(|&f| self.recs[f].pm).unwrap_or(0.0);
        let dd3 = if pm > 0.0 { (1.0 - pp / pm) * 100.0 } else { 0.0 };
        let maxb30 = self.dq30.front().map(|&f| self.recs[f].sol as f64 / 1e9).unwrap_or(0.0);
        // ---- dd1_build extras (the state BEFORE the trade; a sell changes only the per-slot sells and the >= 2% dump time)
        let since_buy = self.last_buy.map(|b| (r.arr - b) / 1000.0).unwrap_or(1e9);
        let ws = &self.ws[r.w as usize];
        let s_buy = ws.buy_sol as f64 / 1e9;
        let s_hold = if ws.nb > 0 { r.s as f64 - ws.first_buy_s as f64 } else { -1.0 };
        let mut c20: [u32; COH20_TRADES] = [0; COH20_TRADES];
        let mut n20 = 0usize;
        for x in &self.recs[k.saturating_sub(COH20_TRADES)..k] {
            if x.buy && r.s - x.s <= COH20_SLOTS && self.users[x.w as usize].1.coh && !c20[..n20].contains(&x.w) { c20[n20] = x.w; n20 += 1; }
        }
        let p_after = r.vsol as f64 / r.vtok as f64;
        let drop_pct = (1.0 - p_after / ((r.vsol as f64 + r.sol as f64) / (r.vtok as f64 - r.tok as f64))) * 100.0;
        let since2 = self.pre_last2.map(|b| (r.arr - b) / 1000.0).unwrap_or(1e9);
        let x = [mv, age, curve, from_bun, ret30, ns1, ns3, net3, dd3, maxb30, self.nwal as f64, self.nhold as f64, self.fhold as f64,
                 since_buy, s_buy, s_hold, self.coh_n as f64, self.coh_sol as f64 / 1e9, n20 as f64, self.bundle_sol as f64 / 1e9,
                 self.pre_ssol_slot as f64 / 1e9, self.pro_after as f64, drop_pct, self.uniq_b as f64, since2];
        Ok(x.map(f32r))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dip_imit::{self as di, Imit, LaunchInfo, TokenBook};
    use std::collections::{HashMap, HashSet};

    fn load_json(p: &str) -> Option<Value> { std::fs::read_to_string(p).ok().and_then(|s| serde_json::from_str(&s).ok()) }

    fn bundle() -> Option<Bundle> {
        let root = env!("CARGO_MANIFEST_DIR");
        for p in [format!("{root}/testdata/dip_m2_bundle.json"), "/home/moiz/sniper-data/strategies/dipdetect/m2_v3_reg4_top25.json".to_string()] {
            if let Ok(b) = Bundle::load(&p) { return Some(b); }
        }
        None
    }

    /// a parity trade: [slot, tx index, event index, sig, user, buy, sol, tok, vsol, vtok, fee bps, creator fee bps]
    fn trade(r: &Value) -> T {
        T { s: r[0].as_u64().unwrap(), i: r[1].as_u64().unwrap() as u32, j: r[2].as_i64().unwrap() as i32, sig: r[3].as_str().unwrap().to_string(),
            user: r[4].as_str().unwrap().to_string(), buy: r[5].as_bool().unwrap(), sol: r[6].as_u64().unwrap(), tok: r[7].as_u64().unwrap(),
            vsol: r[8].as_u64().unwrap(), vtok: r[9].as_u64().unwrap(), fbps: r[10].as_u64().unwrap_or(95) as u32, cbps: r[11].as_u64().unwrap_or(30) as u32, syn: false }
    }

    /// arrival clock, f32 rounding, bins: small exact checks
    #[test]
    fn clock_and_bins() {
        assert_eq!(arrival(10, 0), 2120.0);
        assert_eq!(arrival(10, 200), 2120.0 + 0.5 * 212.0);
        assert_eq!(arrival(10, 999), 2120.0 + (999.0 / 1000.0) * 212.0);
        assert_eq!(f32r(0.1), 0.1f32 as f64);
        let m = Model { name: "t".into(), edges: vec![vec![1.0, 2.0, 3.0]; NF], seeds: vec![] };
        let mut x = [0.0; NF];
        x[0] = 2.0; x[1] = f64::NAN; x[2] = 3.5; x[3] = f64::INFINITY; x[4] = 0.5;
        let b = m.bins(&x);
        assert_eq!((b[0], b[1], b[2], b[3], b[4]), (3, 0, 4, 0, 1));
    }

    /// the out-of-order path (insert + replay) gives the state of the in-order feed
    #[test]
    fn reorder_equals_in_order() {
        let sets = Sets { cohort: FxHashSet::default(), upro: FxHashSet::default(), bots: FxHashMap::default() };
        let mut v: u64 = 30_000_000_000; let mut t: u64 = 1_073_000_000_000_000;
        let mut trs = Vec::new();
        for n in 0..60u64 {
            let buy = n % 3 != 2; let sol = 100_000_000 + n * 7_000_000;
            let tok = if buy { (t as u128 * sol as u128 / (v + sol) as u128) as u64 } else { (t as u128 * sol as u128 / (v - sol) as u128) as u64 };
            if buy { v += sol; t -= tok; } else { v -= sol; t += tok; }
            let mut u = [0u8; 32]; u[0] = (n % 7) as u8 + 1;
            trs.push(Tr { s: 100 + n / 4, i: (n % 4) as u32 * 10, j: 0, buy, sol, tok, vsol: v, vtok: t, user: u });
        }
        let mut a = Tok::new(100);
        for x in &trs { a.push(x, &sets); }
        let mut b = Tok::new(100);
        for (n, x) in trs.iter().enumerate() { if n != 30 { b.push(x, &sets); } }
        b.push(&trs[30], &sets);
        b.push(&trs[59], &sets);   // a duplicate
        b.push(&trs[10], &sets);   // an older duplicate
        assert_eq!(b.reorders, 1);
        assert_eq!(b.dups, 2);
        assert!(b.dirty);
        assert_eq!(a.features().unwrap(), b.features().unwrap());
        assert!(!b.dirty);
        // in-order trades after an out-of-order one (still dirty) and a later replay give the in-order state too
        let mut c = Tok::new(100);
        for (n, x) in trs.iter().enumerate() { if n != 5 { c.push(x, &sets); } if n == 40 { c.push(&trs[5], &sets); } }
        assert_eq!(a.features().unwrap(), c.features().unwrap());
    }

    /// SHRED FIRE (dip14): on the M2 parity tapes, before every real trade a speculative newer sell (by an existing wallet, a new
    /// wallet, a bot of the set) is pushed with push_spec, scored, and rolled back: the state is then exactly the reference state
    /// (every field), the features at every study dump are unchanged, time_feats_at(arrival at index i) equals the features of a
    /// push at index i, and the interval bounds contain the scores (a point interval = the score)
    #[test]
    fn m2_spec_push_rollback() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(par) = load_json(&format!("{root}/testdata/dip_m2_parity.json")) else { eprintln!("dip_m2_parity.json missing: skipped"); return; };
        let Some(b) = bundle() else { eprintln!("M2 bundle missing: skipped"); return; };
        let bot = b.sets.bots.keys().next().copied().unwrap_or([5; 32]);
        let st_dump = |t: &Tok| format!("{:?} {:?} {:?} {:?} {} {} {} {} {} {:?} {:?} {:?} {:?} {:?} {} {} {} {} {} {} {:?} {:?} {:?} {:?} {:?} {} {:?} {} {} {} {} {} {}",
            t.recs, t.users.iter().map(|u| u.0).collect::<Vec<_>>(), t.ws, t.uidx.len(), t.nwal, t.uniq_b, t.coh_n, t.coh_sol, t.bundle_sol, t.p_bun, t.c_sell, t.c_bsol, t.c_ssol,
            t.slot_cur, t.slot_start, t.ssol_slot, t.pre_ssol_slot, t.lo3, t.lo30, t.p30, t.dq3, t.dq30, t.last_buy, t.big_arr, t.last2, t.pro_after,
            { let mut v: Vec<_> = t.bpos.iter().map(|(k, x)| (*k, x.0.to_bits(), x.1.to_bits())).collect(); v.sort(); v }, t.nhold, t.fhold, t.dirty, t.gaps, t.dups, t.reorders);
        let (mut n_spec, mut n_rows, mut n_tf) = (0usize, 0usize, 0usize);
        for tk in par["tokens"].as_array().unwrap().iter().take(150) {
            let s0 = tk["launch"]["slot"].as_u64().unwrap();
            let (mut a, mut c) = (Tok::new(s0), Tok::new(s0));
            let rows: HashMap<usize, &Value> = tk["dumps"].as_array().unwrap().iter().map(|d| (d["k"].as_u64().unwrap() as usize, d)).collect();
            for (k, r) in tk["trades"].as_array().unwrap().iter().enumerate() {
                let t = Tr::from_t(&trade(r)).unwrap();
                for (n, who) in [t.user, [k as u8; 32], bot].into_iter().enumerate() {
                    let spec = Tr { j: t.j + 50 + n as i32, buy: false, sol: 1_500_000_000, tok: t.tok.max(1), vsol: t.vsol, vtok: t.vtok.saturating_add(1), user: who, ..t };
                    c.clean();
                    let ref_state = st_dump(&c);
                    if let Some(ck) = c.push_spec(&spec, &b.sets) {
                        if let Ok(x) = c.features() {
                            // time features at a later index of the same slot = a real push there
                            let (sb, s2) = c.time_feats_at(arrival(spec.s, spec.i + 25));
                            let ck_alt = { c.rollback(ck); c.push_spec(&Tr { i: spec.i + 25, ..spec }, &b.sets).unwrap() };
                            let xa = c.features().unwrap();
                            assert_eq!((xa[TIME_FEATS[0]], xa[TIME_FEATS[1]]), (sb, s2));
                            for j in (0..NF).filter(|j| !TIME_FEATS.contains(j)) { assert_eq!(xa[j].to_bits(), x[j].to_bits(), "feature {} moved with the index", FN[j]); }
                            let (lo, hi) = b.model.score_bounds(&x, &xa);
                            let (s1, s3) = (b.model.score(&x), b.model.score(&xa));
                            assert!(lo <= s1 && s1 <= hi && lo <= s3 && s3 <= hi);
                            assert_eq!(b.model.score_bounds(&x, &x), (s1, s1));
                            n_tf += 1;
                            c.rollback(ck_alt);
                        } else { c.rollback(ck); }
                        assert_eq!(st_dump(&c), ref_state, "rollback changed the state (token {}, trade {k})", tk["mint"]);
                        n_spec += 1;
                    }
                }
                a.push(&t, &b.sets);
                c.push(&t, &b.sets);
                if rows.contains_key(&k) && !t.buy {
                    n_rows += 1;
                    assert_eq!(a.features().map(|x| x.map(f64::to_bits)), c.features().map(|x| x.map(f64::to_bits)), "features at dump row {k}");
                }
            }
            a.clean(); c.clean();
            assert_eq!(st_dump(&a), st_dump(&c));
        }
        eprintln!("m2 spec push: {n_spec} speculative pushes rolled back exactly, {n_rows} dump rows unchanged, time features + bounds checked on {n_tf}");
        assert!(n_spec > 5_000 && n_tf > 1_000);
    }

    /// PARITY with the Python study (dd1_build / p1_build features, the GBDT score): every dump row the study has on the parity
    /// tokens, fed trade by trade through the engine's path (IMIT1 book for the dump events / envelope + this module)
    #[test]
    fn m2_parity_with_python() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(par) = load_json(&format!("{root}/testdata/dip_m2_parity.json")) else { eprintln!("dip_m2_parity.json missing: skipped"); return; };
        let Some(b) = bundle() else { eprintln!("M2 bundle missing: skipped"); return; };
        let imit = Imit::load(&format!("{root}/ops/overnight/sel/IMIT1.json")).or_else(|_| Imit::load("/home/moiz/sniper/ops/overnight/sel/IMIT1.json"));
        let Ok(imit) = imit else { eprintln!("IMIT1.json missing: skipped"); return; };
        let cohort: HashSet<String> = load_json(&format!("{root}/ops/overnight/sel/cohort_train.json")).or_else(|| load_json("/home/moiz/sniper/ops/overnight/sel/cohort_train.json"))
            .and_then(|v| v.as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(|s| s.to_string())).collect())).unwrap_or_default();
        let targets: HashSet<String> = di::TARGETS.iter().map(|s| s.to_string()).collect();
        assert_eq!(par["bundle_sha256"].as_str().unwrap_or(""), b.sha256, "parity file was made with another bundle");
        let thr = par["thr"].as_f64().unwrap();
        let none = |_s: u64| None;
        let (mut rows, mut feat_bad, mut score_bad, mut worst, mut env_rows) = (0usize, 0usize, 0usize, 0f64, 0usize);
        let mut per_feat = [0usize; NF];
        let mut examples: Vec<String> = Vec::new();
        let (mut py_env_no_event, mut py_env_no_eval, mut env_disagree, mut py_env_n, mut extra_n) = (0usize, 0usize, 0usize, 0usize, 0usize);
        // Stage A picks: [study, engine path with the IMIT1 dump events only, engine path + M2 extra dumps]; both = study & engine
        let (mut picks, mut both) = ([0usize; 3], [0usize; 2]);
        let (mut ns, mut s_us) = (0usize, Vec::<f64>::new());
        let (mut sx, mut sy, mut sxx, mut syy, mut sxy) = (0f64, 0f64, 0f64, 0f64, 0f64);
        for tk in par["tokens"].as_array().unwrap() {
            let la = &tk["launch"];
            let c = LaunchInfo { slot: la["slot"].as_u64().unwrap(), idx: la["idx"].as_u64().map(|v| v as u32), creator: la["creator"].as_str().map(|s| s.to_string()),
                                 signer: la["user"].as_str().map(|s| s.to_string()), sig: la["sig"].as_str().unwrap_or("").to_string(), mayhem: false };
            let want: HashMap<usize, &Value> = tk["dumps"].as_array().unwrap().iter().map(|d| (d["k"].as_u64().unwrap() as usize, d)).collect();
            let mut book = TokenBook::new(c.clone());
            let mut st = Tok::new(c.slot);
            for (k, r) in tk["trades"].as_array().unwrap().iter().enumerate() {
                let t = trade(r);
                let tr = Tr::from_t(&t).unwrap();
                // the engine's path: the IMIT1 book finds the dump events (+ the M2 extra dumps: later big sells of a dump slot) and
                // checks the envelope; M2 scores in-envelope dumps
                let dump_k = book.push(t, &targets, 1800.0, &none);
                let extra_k = if dump_k.is_none() { book.later_in_slot((tr.s, tr.i, tr.j), 1800.0) } else { None };
                st.push(&tr, &b.sets);
                let ev = dump_k.map(|dk| (dk, false)).or(extra_k.map(|dk| (dk, true)));
                let env_ok = ev.map(|(dk, ex)| { let d = book.dump("m", dk, &imit, &cohort, &none); (d.env_ok, d.launch_ok, ex) });
                let py = want.get(&k);
                // the study's rows: features + score at EVERY candidate dump (in or out of the envelope)
                if let Some(py) = py {
                    let t0 = std::time::Instant::now();
                    let x = st.features().expect("a dump row is a sell");
                    let s = b.model.score(&x);
                    s_us.push(t0.elapsed().as_secs_f64() * 1e6); ns += 1;
                    let pf: Vec<f64> = py["x"].as_array().unwrap().iter().map(|v| num(v).unwrap()).collect();
                    rows += 1;
                    let bad: Vec<usize> = (0..NF).filter(|&j| x[j] != pf[j]).collect();
                    for &j in &bad { per_feat[j] += 1; }
                    if !bad.is_empty() {
                        feat_bad += 1;
                        if examples.len() < 12 { examples.push(format!("{} k={k}: {:?}", tk["mint"].as_str().unwrap_or("?"), bad.iter().map(|&j| (FN[j], x[j], pf[j])).collect::<Vec<_>>())); }
                    }
                    let ps = num(&py["score"]).unwrap();
                    let d = (s - ps).abs(); worst = worst.max(d);
                    if d > 1e-9 { score_bad += 1; }
                    sx += s; sy += ps; sxx += s * s; syy += ps * ps; sxy += s * ps;
                    let py_env = py["env"].as_bool().unwrap();
                    if py_env { py_env_n += 1; }
                    let pp = py_env && ps >= thr;
                    let (e_ok, l_ok, ex) = env_ok.unwrap_or((false, false, false));
                    if py_env && !env_ok.is_some_and(|x| !x.2) { py_env_no_event += 1; }
                    if py_env && env_ok.is_none() {
                        py_env_no_eval += 1;
                        if examples.len() < 16 { examples.push(format!("study-envelope dump not evaluated: {} k={k} slot {} sell {}", tk["mint"].as_str().unwrap_or("?"), tr.s, tr.sol)); }
                    }
                    if env_ok.is_some() && e_ok != py_env {
                        env_disagree += 1;
                        if examples.len() < 16 { examples.push(format!("envelope differs: {} k={k} study {py_env} engine {e_ok} (age {} drop {} since_buy {} sell {})", tk["mint"].as_str().unwrap_or("?"), x[1], x[22], x[13], tr.sol)); }
                    }
                    let rp = e_ok && l_ok && s >= thr;
                    if e_ok { env_rows += 1; extra_n += ex as usize; }
                    picks[0] += pp as usize; picks[1] += (rp && !ex) as usize; picks[2] += rp as usize;
                    both[0] += (pp && rp && !ex) as usize; both[1] += (pp && rp) as usize;
                }
            }
        }
        let n = rows as f64;
        let corr = (n * sxy - sx * sy) / ((n * sxx - sx * sx).sqrt() * (n * syy - sy * sy).sqrt());
        s_us.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let pct = |q: f64| s_us.get(((s_us.len() as f64 - 1.0) * q) as usize).copied().unwrap_or(0.0);
        eprintln!("m2 parity: {rows} study dump rows ({py_env_n} in the study envelope), feature mismatches {feat_bad}, score mismatches (>1e-9) {score_bad}, worst |dscore| {worst:e}, corr {corr:.12}");
        eprintln!("  mismatches per feature: {:?}", (0..NF).filter(|&j| per_feat[j] > 0).map(|j| (FN[j], per_feat[j])).collect::<Vec<_>>());
        for e in &examples { eprintln!("  e.g. {e}"); }
        eprintln!("  engine path: in-envelope dumps evaluated {env_rows} ({extra_n} of them M2 extra dumps); study-envelope dumps that are no IMIT1 dump event {py_env_no_event}, \
                   not evaluated even with the extra dumps {py_env_no_eval}; envelope disagreements {env_disagree}");
        let agree = |w: usize| both[w - 1] as f64 / (picks[0] + picks[w] - both[w - 1]).max(1) as f64;
        eprintln!("  Stage A picks (thr {thr}): study {}, engine IMIT1 dump events only {} (both {}, agreement {:.4}), engine + M2 extra dumps {} (both {}, agreement {:.4})",
                  picks[0], picks[1], both[0], agree(1), picks[2], both[1], agree(2));
        let union = picks[0] + picks[2] - both[1];
        let both_pick = both[1];
        eprintln!("  features + score time (debug or release as built): p50 {:.1} us, p99 {:.1} us, max {:.1} us over {ns}", pct(0.5), pct(0.99), pct(1.0));
        assert!(rows > 1000, "too few parity rows");
        assert!(corr >= 0.99, "score correlation below 0.99");
        assert!(both_pick as f64 >= 0.95 * union.max(1) as f64, "Stage A pick agreement below 95%");
        assert!(feat_bad * 1000 <= rows, "more than 0.1% of rows have a feature mismatch");
        assert!(score_bad * 1000 <= rows, "more than 0.1% of rows have a score mismatch");
    }
}
