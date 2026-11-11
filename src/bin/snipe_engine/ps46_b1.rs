// =====================================================================================================================
// dip46 B1 LOG shadow (owner-approved "B1 LOG PLAN v1"; LOG ONLY: nothing sent, armed, skipped, sized or changed; the engine reads
// nothing back). Lives inside the dip45 fleet thread (ps45_fleet.rs; needs --presend-live-fleet-log on) because its gate is the fleet
// SIGNATURE detector's flags. Off (the default) = nothing of it exists. Docs: docs/dip46_b1.md. Audit: ~/sniper-studies/push4-audit/REPORT.md.
//
//  1. FEATURES. Every executed pump trade (all tokens) feeds a per-token state; when the executed feed's slot clock moves past a slot
//     in which a token traded, the token-slot query (token, S = that slot + 1) is scored with the 25 arm-time features of
//     push-l5/snap2.py (trades strictly before S only: causal), exactly as ops/fleet45/b1_lib.py features_at.
//  2. SCORE. The frozen B0 model (push-l5/opt2 FROZEN.md; FINAL train): decoder (HGB classifier, 25 features) >= 0.2, then the
//     regressor (HGB, "lite" + decoder score) = the expected 8-slot window value (SOL). Built in (testdata/dip46_b1_model.json, its
//     sha256 = FROZEN_SHA256) or --presend-live-b1-model FILE (must have the same sha256). Exact sklearn tree walk and summation order.
//  3. RULES. B0 = decoder >= 0.2 and value >= 2 mSOL (frozen); B1 = decoder >= 0.2 and value >= 0 AND a fleet-signature try on the
//     token in slots S-2..S-1 (fleet flags n2 > 0). One 8-slot window [S, S+7] per token at a time, per rule (push-l5 make_windows).
//  4. OUTCOME (paper, push-l5 outcomes + push2-d sim_one): the first dump (a run of sells of the token in one slot, >= 3% drop and
//     >= 0.3 SOL) with drop >= 10% in the window fills at position i1 + 26 behind it (next slot past the slot's last pump index + 20),
//     0.8 SOL, exit at the start of slot entry + 3; later-buy SOL and buyers in [entry, entry + 3 slots).
//  5. RECORD "presend_live_b1" stage "window" per opened window (B0 or B1), written when the window is settled: the features (f),
//     scores, rule passes, gate flags, kind (t2 / rearm / other by cls_of), live armed / filled on the token in the window (our live or
//     dry presend_live_arm / _fill), overlap same / new, the fill (dump, entry, exit slot, paper SOL, later-buy SOL / buyers),
//     model_sha, feat_hash. "config" at the start; status part "B1 LOG"; run_end fleet.b1.
// =====================================================================================================================
use super::*;
use super::ps45_fleet::Flags;
use sha2::Digest;
use std::collections::BTreeMap;

pub const FROZEN_JSON: &str = include_str!("../../../testdata/dip46_b1_model.json");
pub const FROZEN_SHA256: &str = "7158769d53d270f9fdd1c9949da3fd52aa9fd61aac2efedfea5c51d5244aa690";
pub const F0: [&str; 25] = ["age", "vsol", "last_buy", "last_pct", "last_gap", "bb5", "bs5", "ntr5", "busy", "nbuyers", "bsol100", "ssol100", "runup", "ddhigh", "top1",
    "top1_age", "top3", "n_ge2", "n_ge4", "n_ge6", "sum_ge2", "cr_bal", "n_prev_dumps", "last_dump_gap", "last_dump_spct"];
pub const LITE: [&str; 12] = ["age", "vsol", "bb5", "bs5", "ntr5", "runup", "ddhigh", "nbuyers", "busy", "n_prev_dumps", "last_dump_gap", "score"];
/// trades kept per token (slots; the features look back 100)
pub const KEEP_SLOTS: u64 = 110;
/// an idle token is forgotten after (slots, ~24 h): the holder / dump / launch history must survive long quiet spells (parity: tokens
/// revived after 8 h); its trade list is already cut to the last KEEP_SLOTS
pub const IDLE_SLOTS: u64 = 403_200;
/// our live arms / fills kept per token (slots)
const LIVE_KEEP: u64 = 128;
pub const FEE: f64 = 0.0125;
const KSTD: f64 = 3.219e25;

pub fn hex(b: &[u8]) -> String { b.iter().map(|x| format!("{x:02x}")).collect() }
pub fn sha256_hex(b: &[u8]) -> String { hex(&sha2::Sha256::digest(b)) }
/// first 16 hex of sha256 over the values as little-endian f64 (b1_lib.feat_hash)
pub fn feat_hash(f: &[f64]) -> String {
    let mut h = sha2::Sha256::new();
    for x in f { h.update(x.to_le_bytes()); }
    hex(&h.finalize()[..8])
}
/// the feature schema's hash (b1_lib.schema_hash)
pub fn schema_hash() -> String { hex(&sha2::Sha256::digest(format!("{}|{}", F0.join(","), LITE.join(",")).as_bytes())[..8]) }

// ---- the model ------------------------------------------------------------------------------------------------------------

pub struct Tree { f: Vec<usize>, t: Vec<f64>, l: Vec<usize>, r: Vec<usize>, leaf: Vec<bool>, v: Vec<f64>, ml: Vec<bool> }
pub struct Gbm { pub base: f64, pub trees: Vec<Tree>, pub features: Vec<String> }

fn bits(v: &serde_json::Value) -> Result<f64> { v.as_u64().map(f64::from_bits).ok_or_else(|| anyhow::anyhow!("a float's bits (u64) expected")) }

impl Gbm {
    fn parse(j: &serde_json::Value) -> Result<Gbm> {
        let features: Vec<String> = j["features"].as_array().ok_or_else(|| anyhow::anyhow!("features"))?.iter().filter_map(|x| x.as_str().map(String::from)).collect();
        let mut trees = Vec::new();
        for t in j["trees"].as_array().ok_or_else(|| anyhow::anyhow!("trees"))? {
            let u = |k: &str| -> Result<Vec<u64>> { t[k].as_array().ok_or_else(|| anyhow::anyhow!("tree.{k}"))?.iter().map(|x| x.as_u64().ok_or_else(|| anyhow::anyhow!("tree.{k}"))).collect() };
            let fl = |k: &str| -> Result<Vec<f64>> { t[k].as_array().ok_or_else(|| anyhow::anyhow!("tree.{k}"))?.iter().map(bits).collect() };
            let tr = Tree { f: u("f")?.into_iter().map(|x| x as usize).collect(), t: fl("t")?, l: u("l")?.into_iter().map(|x| x as usize).collect(),
                r: u("r")?.into_iter().map(|x| x as usize).collect(), leaf: u("leaf")?.into_iter().map(|x| x != 0).collect(), v: fl("v")?, ml: u("ml")?.into_iter().map(|x| x != 0).collect() };
            let n = tr.f.len();
            if [tr.t.len(), tr.l.len(), tr.r.len(), tr.leaf.len(), tr.v.len(), tr.ml.len()].iter().any(|&x| x != n) || n == 0 { bail!("a tree's arrays differ in length"); }
            for k in 0..n { if !tr.leaf[k] && (tr.l[k] >= n || tr.r[k] >= n || tr.f[k] >= features.len()) { bail!("a tree's node points outside"); } }
            trees.push(tr);
        }
        Ok(Gbm { base: bits(&j["baseline"])?, trees, features })
    }
    /// sklearn HistGradientBoosting raw prediction: baseline, then each tree in order (x <= threshold goes left; NaN by missing_go_to_left)
    pub fn raw(&self, x: &[f64]) -> f64 {
        let mut s = self.base;
        for t in &self.trees {
            let mut k = 0usize;
            while !t.leaf[k] {
                let xv = x[t.f[k]];
                k = if xv.is_nan() { if t.ml[k] { t.l[k] } else { t.r[k] } } else if xv <= t.t[k] { t.l[k] } else { t.r[k] };
            }
            s += t.v[k];
        }
        s
    }
}

pub struct Model { pub dec: Gbm, pub reg: Gbm, pub sha: String, pub src: String, pub dec_min: f64, pub b0_thr: f64, pub b1_thr: f64, pub window: u64, pub size: f64, pub dp: u32,
    pub hold: u64, pub drop: f64, pub cost_slot: f64, pub rule: serde_json::Value }

impl Model {
    pub fn parse(raw: &[u8], src: &str) -> Result<Model> {
        let j: serde_json::Value = serde_json::from_slice(raw)?;
        let (dec, reg) = (Gbm::parse(&j["dec"])?, Gbm::parse(&j["reg"])?);
        if dec.features != F0 { bail!("the decoder's features are not the 25 F0 features in order"); }
        if reg.features != LITE { bail!("the regressor's features are not lite + score in order"); }
        let r = &j["rule"];
        let f = |k: &str| r[k].as_f64().ok_or_else(|| anyhow::anyhow!("rule.{k}"));
        Ok(Model { dec, reg, sha: sha256_hex(raw), src: src.into(), dec_min: f("dec_min")?, b0_thr: f("b0_thr")?, b1_thr: f("b1_thr")?, window: f("window")? as u64,
            size: f("size_sol")?, dp: f("dp")? as u32, hold: f("hold")? as u64, drop: f("drop")?, cost_slot: f("cost_slot_sol")?, rule: r.clone() })
    }
    pub fn frozen() -> Model { Model::parse(FROZEN_JSON.as_bytes(), "built-in").expect("the built-in B0 model") }
    /// a model file: must be the frozen one (sha256)
    pub fn load(path: &str) -> Result<Model> {
        let raw = std::fs::read(path).map_err(|e| anyhow::anyhow!("--presend-live-b1-model {path}: {e}"))?;
        let sha = sha256_hex(&raw);
        if sha != FROZEN_SHA256 { bail!("--presend-live-b1-model {path}: sha256 {sha} is not the frozen B0 model's {FROZEN_SHA256}"); }
        Model::parse(&raw, path)
    }
    /// (decoder probability, regressor value when the decoder passes)
    pub fn score(&self, f: &[f64; 25]) -> (f64, Option<f64>) {
        let p = 1.0 / (1.0 + (-self.dec.raw(f)).exp());
        if p < self.dec_min { return (p, None); }
        let x = [f[0], f[1], f[5], f[6], f[7], f[12], f[13], f[9], f[8], f[22], f[23], p];
        (p, Some(self.reg.raw(&x)))
    }
}

/// push-l5 cls_of: t2 (bb5 >= 3 and bs5 < 2), rearm (bs5 >= 2), other
pub fn kind_of(f: &[f64; 25]) -> &'static str { if f[5] >= 3.0 && f[6] < 2.0 { "t2" } else if f[6] >= 2.0 { "rearm" } else { "other" } }

// ---- the per-token state ---------------------------------------------------------------------------------------------------

#[derive(Clone, Copy, Debug)]
pub struct BT { pub slot: u64, pub idx: u32, pub j: u16, pub user: Pk, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64 }
impl BT {
    pub fn pos(&self) -> (u64, u32, u16) { (self.slot, self.idx, self.j) }
    fn g(&self) -> f64 { if self.buy { 1.0 } else { -1.0 } }
    pub fn pa(&self) -> f64 { self.vsol as f64 / self.vtok as f64 }
    pub fn pb(&self) -> f64 { (self.vsol as f64 - self.g() * self.sol as f64) / (self.vtok as f64 + self.g() * self.tok as f64) }
    pub fn pct(&self) -> f64 { self.tok as f64 / 1e13 }
    fn std(&self) -> bool { let k = self.vsol as f64 * self.vtok as f64 / KSTD; k > 0.97 && k < 1.03 }
}

#[derive(Clone, Debug)]
struct Run { slot: u64, i0: u32, pb0: f64, last: BT, sol: f64, sellers: Vec<(Pk, f64)> }

#[derive(Clone, Copy, Debug)]
pub struct Dump { pub slot: u64, pub i0: u32, pub i1: u32, pub drop: f64, pub spct: f64, pub sol: f64, pub q: (u64, u32, u16), pub vsol: u64, pub vtok: u64 }

#[derive(Default)]
pub struct Tok {
    pub trades: VecDeque<BT>,
    /// wallet -> (balance % of supply, first buy slot)
    bal: FxHashMap<Pk, (f64, Option<u64>)>,
    pub cslot: Option<u64>,
    pub creator: Option<Pk>,
    run: Option<Run>,
    pub n_dumps: u32,
    pub last_dump: Option<(u64, f64)>,
    /// recent >= 10% dumps (window fills)
    pub big: VecDeque<Dump>,
    pub last_slot: u64,
    /// trades on the standard pump curve (k within 3% of the default), of all (the tape's 90 % rule, running)
    n_std: u32,
    n_all: u32,
    until_b0: u64,
    until_b1: u64,
    /// our live / dry arms [from, to] and fills (slot)
    live_arms: Vec<(u64, u64)>,
    live_fills: Vec<u64>,
    pub open_w: u32,
    pub late: u32,
}

impl Tok {
    fn close_run(&mut self, drop_min: f64) -> Option<Dump> {
        let r = self.run.take()?;
        let drop = 1.0 - r.last.pa() / r.pb0;
        if !(drop >= 0.03 && r.sol >= 0.3) { return None; }
        let mut best = 0usize;
        for (k, s) in r.sellers.iter().enumerate() { if s.1 > r.sellers[best].1 { best = k; } }
        let d = Dump { slot: r.slot, i0: r.i0, i1: r.last.idx, drop, spct: r.sellers[best].1 / 1e13, sol: r.sol, q: r.last.pos(), vsol: r.last.vsol, vtok: r.last.vtok };
        self.n_dumps += 1;
        self.last_dump = Some((d.slot, d.spct));
        if drop >= drop_min { self.big.push_back(d); while self.big.len() > 16 { self.big.pop_front(); } }
        Some(d)
    }

    /// one trade in chain order; a closed dump comes back
    fn add(&mut self, x: BT, drop_min: f64) -> Option<Dump> {
        let late = self.trades.back().is_some_and(|y| y.pos() > x.pos());
        let e = self.bal.entry(x.user).or_insert((0.0, None));
        e.0 += if x.buy { x.pct() } else { -x.pct() };
        if x.buy && e.1.is_none() { e.1 = Some(x.slot); }
        if late {
            self.late += 1;
            let k = self.trades.partition_point(|y| y.pos() < x.pos());
            self.trades.insert(k, x);
            return None;
        }
        let mut done = None;
        let cont = !x.buy && self.run.as_ref().is_some_and(|r| r.slot == x.slot);
        if !cont { done = self.close_run(0.10); }
        if !x.buy {
            let r = self.run.get_or_insert_with(|| Run { slot: x.slot, i0: x.idx, pb0: x.pb(), last: x, sol: 0.0, sellers: Vec::new() });
            r.last = x; r.sol += x.sol as f64 / 1e9;
            match r.sellers.iter_mut().find(|s| s.0 == x.user) { Some(s) => s.1 += x.tok as f64, None => r.sellers.push((x.user, x.tok as f64)) }
        }
        let _ = drop_min;
        self.trades.push_back(x);
        self.last_slot = self.last_slot.max(x.slot);
        self.n_all += 1;
        if x.std() { self.n_std += 1; }
        done
    }

    /// the 25 F0 features at slot qs (trades strictly before qs); None without a trade
    pub fn features(&self, qs: u64) -> Option<[f64; 25]> {
        let tr = &self.trades;
        let hi = tr.partition_point(|x| x.slot < qs);
        if hi == 0 { return None; }
        let lo = tr.partition_point(|x| x.slot < qs.saturating_sub(100)).min(hi - 1);
        let l5 = tr.partition_point(|x| x.slot < qs.saturating_sub(5));
        let last = tr[hi - 1];
        let (mut bb5, mut bs5) = (None::<f64>, None::<f64>);
        for x in tr.range(l5..hi) {
            let p = x.pct();
            if x.buy { bb5 = Some(bb5.map_or(p, |m| m.max(p))); } else { bs5 = Some(bs5.map_or(p, |m| m.max(p))); }
        }
        let (mut bsol, mut ssol, mut mx) = (0.0f64, 0.0f64, f64::NEG_INFINITY);
        let mut buyers: Vec<Pk> = Vec::new();
        for x in tr.range(lo..hi) {
            if x.buy { bsol += x.sol as f64 / 1e9; buyers.push(x.user); } else { ssol += x.sol as f64 / 1e9; }
            mx = mx.max(x.pa());
        }
        buyers.sort_unstable(); buyers.dedup();
        // holders: every wallet but the creator above 0.05 %
        let mut ex: Vec<(f64, Option<u64>)> = self.bal.iter().filter(|(w, v)| Some(**w) != self.creator && v.0 > 0.05).map(|(_, v)| *v).collect();
        ex.sort_by(|a, b| b.0.total_cmp(&a.0));
        let top = &ex[..ex.len().min(3)];
        let (mut n2, mut n4, mut n6, mut s2) = (0.0, 0.0, 0.0, 0.0);
        for v in &ex { if v.0 >= 2.0 { n2 += 1.0; s2 += v.0; } if v.0 >= 4.0 { n4 += 1.0; } if v.0 >= 6.0 { n6 += 1.0; } }
        let mut top3 = 0.0; for v in top { top3 += v.0; }
        // the dumps strictly before qs (an open run of an earlier slot is complete: counted)
        let (mut nd, mut ld) = (self.n_dumps, self.last_dump);
        if let Some(r) = &self.run {
            if r.slot < qs {
                let drop = 1.0 - r.last.pa() / r.pb0;
                if drop >= 0.03 && r.sol >= 0.3 {
                    let mut best = 0usize;
                    for (k, s) in r.sellers.iter().enumerate() { if s.1 > r.sellers[best].1 { best = k; } }
                    nd += 1; ld = Some((r.slot, r.sellers[best].1 / 1e13));
                }
            }
        }
        Some([
            self.cslot.map_or(-1.0, |c| qs as f64 - c as f64), last.vsol as f64 / 1e9, if last.buy { 1.0 } else { 0.0 }, last.pct(), (qs - last.slot) as f64,
            bb5.unwrap_or(0.0), bs5.unwrap_or(0.0), (hi - l5) as f64, (hi - lo) as f64, buyers.len() as f64, bsol, ssol,
            last.pb() / tr[lo].pb(), last.pb() / mx,
            top.first().map_or(0.0, |v| v.0), top.first().map_or(-1.0, |v| v.1.map_or(-1.0, |s| qs as f64 - s as f64)), top3, n2, n4, n6, s2,
            self.creator.and_then(|c| self.bal.get(&c)).map_or(0.0, |v| v.0),
            nd as f64, ld.map_or(1e6, |d| (qs - d.0) as f64), ld.map_or(0.0, |d| d.1),
        ])
    }
}

// ---- the windows ------------------------------------------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct Fill { pub dump: Dump, pub es: u64, pub ei: u32, pub paper: f64, pub lb: f64, pub nbuy: u32 }

#[derive(Clone, Debug)]
pub struct Win {
    pub mint: Pk, pub s: u64, pub last: (u64, u32), pub f: [f64; 25], pub dec: f64, pub val: Option<f64>, pub b0: bool, pub b1: bool, pub open_b0: bool, pub open_b1: bool,
    pub flags: Flags, pub eval_slot: u64, pub clock: u64, pub t: u64, pub dump: Option<Dump>, pub fill: Option<Fill>,
}

#[derive(Default, Clone, Debug)]
pub struct B1Stats { pub trades: u64, pub creates: u64, pub late: u64, pub queries: u64, pub nonstd: u64, pub dec_pass: u64, pub b0_pass: u64, pub b1_pass: u64, pub gate_rows: u64,
    pub win_b0: u64, pub win_b1: u64, pub fills_b0: u64, pub fills_b1: u64, pub paper_b0: f64, pub paper_b1: f64, pub new_b1: u64, pub fills_new_b1: u64, pub paper_new_b1: f64,
    pub closed: u64, pub max_lag: u64, pub toks: u64 }

pub struct B1 {
    pub m: Model,
    pub toks: FxHashMap<Pk, Tok>,
    /// tokens that traded in the executed clock's current slot
    dirty: Vec<Pk>,
    /// the executed feed's slot clock (highest trade slot)
    pub cur: u64,
    /// last pump tx index per slot
    smax: BTreeMap<u64, u32>,
    pub wins: Vec<Win>,
    pub st: B1Stats,
    /// tests: every query (token, slot, features, decoder, value)
    pub trace: Option<Vec<(Pk, u64, [f64; 25], f64, Option<f64>)>>,
    /// tests: a window at every query (no rule, no one-per-token)
    pub all_windows: bool,
}

impl B1 {
    pub fn new(m: Model) -> B1 {
        B1 { m, toks: FxHashMap::default(), dirty: Vec::new(), cur: 0, smax: BTreeMap::new(), wins: Vec::new(), st: B1Stats::default(), trace: None, all_windows: false }
    }

    pub fn config_rec(&self) -> serde_json::Value {
        serde_json::json!({"ev": "presend_live_b1", "stage": "config", "mode": "log", "model_src": self.m.src, "model_sha": self.m.sha, "frozen_sha": FROZEN_SHA256,
            "feat_schema": schema_hash(), "features": F0, "reg_features": LITE, "rule": self.m.rule, "keep_slots": KEEP_SLOTS,
            "b0": format!("decoder >= {} and value >= {} SOL", self.m.dec_min, self.m.b0_thr), "b1": format!("decoder >= {} and value >= {} SOL and fleet n2 > 0", self.m.dec_min, self.m.b1_thr)})
    }

    pub fn create(&mut self, slot: u64, c: &arbx::dip::CreateEvent) {
        self.st.creates += 1;
        let t = self.toks.entry(c.mint).or_default();
        if t.cslot.is_none() { t.cslot = Some(slot); t.creator = Some(c.creator); }
    }

    /// one executed tx's pump events (chain order inside the tx); the slot clock moves first
    pub fn exec(&mut self, slot: u64, idx: u32, trades: &[arbx::dip::TradeEvent], creates: &[arbx::dip::CreateEvent], t: u64, clock: u64,
                flags: &dyn Fn(&Pk, u64) -> Flags, out: &mut Vec<serde_json::Value>) {
        if slot > self.cur { self.advance(slot, t, clock, flags, out); }
        for c in creates { self.create(slot, c); }
        if trades.is_empty() { return; }
        let e = self.smax.entry(slot).or_insert(idx); *e = (*e).max(idx);
        for (j, e) in trades.iter().enumerate() {
            if e.tok == 0 || e.vtok == 0 { continue; }
            self.st.trades += 1;
            let x = BT { slot, idx, j: j as u16, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok };
            let tok = self.toks.entry(e.mint).or_default();
            let was = tok.late;
            let d = tok.add(x, self.m.drop);
            if tok.late > was { self.st.late += 1; }
            if slot >= self.cur && !self.dirty.contains(&e.mint) { self.dirty.push(e.mint); }
            if let Some(d) = d { self.on_dump(&e.mint, d); }
        }
    }

    /// a >= 10% dump closed: the open windows of the token fill on it (the first one in the window)
    fn on_dump(&mut self, m: &Pk, d: Dump) {
        if d.drop < self.m.drop { return; }
        let w_end = self.m.window - 1;
        for w in self.wins.iter_mut().filter(|w| w.mint == *m && w.dump.is_none() && w.s <= d.slot && d.slot <= w.s + w_end) { w.dump = Some(d); }
    }

    /// the executed clock reached `slot`: the earlier slots are complete. Runs close, token-slot queries are scored, windows settle.
    pub fn advance(&mut self, slot: u64, t: u64, clock: u64, flags: &dyn Fn(&Pk, u64) -> Flags, out: &mut Vec<serde_json::Value>) {
        let prev = self.cur;
        self.cur = slot;
        let dirty = std::mem::take(&mut self.dirty);
        for m in &dirty {
            let d = self.toks.get_mut(m).and_then(|t| if t.run.as_ref().is_some_and(|r| r.slot < slot) { t.close_run(self.m.drop) } else { None });
            if let Some(d) = d { self.on_dump(m, d); }
        }
        for m in &dirty { self.query(m, t, clock, flags); }
        self.settle(false, out);
        if prev / 64 != slot / 64 { self.prune(); }
    }

    fn query(&mut self, m: &Pk, t: u64, clock: u64, flags: &dyn Fn(&Pk, u64) -> Flags) {
        let Some(tok) = self.toks.get(m) else { return };
        let qs = tok.last_slot + 1;
        if (tok.n_std as u64) * 10 < (tok.n_all as u64) * 9 { self.st.nonstd += 1; return; }
        let Some(f) = tok.features(qs) else { return };
        self.st.queries += 1;
        let (dec, val) = self.m.score(&f);
        if let Some(tr) = self.trace.as_mut() { tr.push((*m, qs, f, dec, val)); }
        let last = tok.trades.iter().rev().find(|x| x.slot < qs).map(|x| (x.slot, x.idx)).unwrap_or((0, 0));
        let fl = flags(m, qs);
        let gate = fl.n2 > 0;
        let b0 = val.is_some_and(|v| v >= self.m.b0_thr);
        let b1 = val.is_some_and(|v| v >= self.m.b1_thr) && gate;
        if val.is_some() { self.st.dec_pass += 1; }
        if b0 { self.st.b0_pass += 1; }
        if b1 { self.st.b1_pass += 1; }
        if gate { self.st.gate_rows += 1; }
        let tok = self.toks.get_mut(m).unwrap();
        let (open_b0, open_b1) = if self.all_windows { (true, true) } else { (b0 && qs > tok.until_b0, b1 && qs > tok.until_b1) };
        if !(open_b0 || open_b1) { return; }
        let wend = qs + self.m.window - 1;
        if open_b0 && !self.all_windows { tok.until_b0 = wend; }
        if open_b1 && !self.all_windows { tok.until_b1 = wend; }
        tok.open_w += 1;
        self.st.max_lag = self.st.max_lag.max(clock.saturating_sub(qs));
        self.wins.push(Win { mint: *m, s: qs, last, f, dec, val, b0, b1, open_b0, open_b1, flags: fl, eval_slot: self.cur, clock, t, dump: None, fill: None });
    }

    /// windows whose outcome is known (all = the run's end / the tests' flush)
    fn settle(&mut self, all: bool, out: &mut Vec<serde_json::Value>) {
        let cur = self.cur;
        let w_end = self.m.window - 1;
        let hold = self.m.hold;
        let mut k = 0;
        while k < self.wins.len() {
            let w = &self.wins[k];
            let done = all || match &w.dump {
                None => cur > w.s + w_end,
                // the entry slot is s0 or s0 + 1: settle once the clock passes s0 + 1 + hold
                Some(d) => cur > d.slot + 1 + hold,
            };
            if !done { k += 1; continue; }
            let mut w = self.wins.swap_remove(k);
            if let Some(d) = w.dump { w.fill = self.paper(&w.mint, d); }
            let r = self.window_rec(&w, !all || cur > w.s + w_end + 1 + hold);
            out.push(r);
            if let Some(t) = self.toks.get_mut(&w.mint) { t.open_w = t.open_w.saturating_sub(1); }
        }
    }

    /// push2-d sim_one (fol 1) on the token's trades
    pub fn paper(&self, m: &Pk, d: Dump) -> Option<Fill> {
        let tok = self.toks.get(m)?;
        let tr = &tok.trades;
        let q = tr.iter().position(|x| x.pos() == d.q)?;
        let blen = self.smax.get(&d.slot).map_or(1200, |&x| x as u64) + 20;
        let k = (d.vsol as f64 / 1e9) * d.vtok as f64;
        let pos = d.i1 as u64 + self.m.dp as u64;
        let (es, ei) = if pos <= blen { (d.slot, pos) } else { (d.slot + 1, pos - blen) };
        let mut e = q;
        while e + 1 < tr.len() && (tr[e + 1].slot < es || (tr[e + 1].slot == es && tr[e + 1].idx as u64 <= ei)) { e += 1; }
        let (vs, vt) = (tr[e].vsol as f64 / 1e9, tr[e].vtok as f64);
        let size = self.m.size;
        let mut vs2 = vs + size; let mut vt2 = k / vs2; let mytok = vt - vt2;
        let cost = size * (1.0 + FEE) + 0.0002 + 0.000005;
        let (mut lb, mut buyers) = (0.0f64, Vec::<Pk>::new());
        let mut x = e + 1;
        while x < tr.len() && tr[x].slot < es + self.m.hold {
            let y = tr[x];
            if y.buy { vs2 += y.sol as f64 / 1e9; vt2 = k / vs2; lb += y.sol as f64 / 1e9; buyers.push(y.user); } else { vt2 += y.tok as f64; vs2 = k / vt2; }
            x += 1;
        }
        buyers.sort_unstable(); buyers.dedup();
        let paper = (vs2 - k / (vt2 + mytok)) * (1.0 - FEE) - 0.0006 - cost;
        Some(Fill { dump: d, es, ei: ei as u32, paper, lb, nbuy: buyers.len() as u32 })
    }

    fn window_rec(&mut self, w: &Win, complete: bool) -> serde_json::Value {
        let tok = self.toks.get(&w.mint);
        let end = w.s + self.m.window - 1;
        let live_armed = tok.is_some_and(|t| t.live_arms.iter().any(|a| a.0 <= end && a.1 >= w.s));
        let live_filled = tok.is_some_and(|t| t.live_fills.iter().any(|&s| s >= w.s && s <= end));
        let new = !(live_armed || live_filled);
        let kind = kind_of(&w.f);
        let fl = &w.fill;
        self.st.closed += 1;
        if w.open_b0 { self.st.win_b0 += 1; if let Some(f) = fl { self.st.fills_b0 += 1; self.st.paper_b0 += f.paper; } }
        if w.open_b1 {
            self.st.win_b1 += 1;
            if let Some(f) = fl { self.st.fills_b1 += 1; self.st.paper_b1 += f.paper; }
            if new { self.st.new_b1 += 1; if let Some(f) = fl { self.st.fills_new_b1 += 1; self.st.paper_new_b1 += f.paper; } }
        }
        let late = tok.map_or(0, |t| t.late);
        let mut r = serde_json::json!({"ev": "presend_live_b1", "stage": "window", "mint": b58(&w.mint), "slot": w.s, "idx": w.last.1, "last": [w.last.0, w.last.1], "end_slot": end,
            "kind": kind, "dec_score": w.dec, "b0_score": w.val, "b0_pass": w.b0, "b1_pass": w.b1, "opens": {"b0": w.open_b0, "b1": w.open_b1},
            "gate_on2": w.flags.n2 > 0, "gate_on8": w.flags.n8 > 0, "gate_pre8": w.flags.pre8, "gate": w.flags.json(w.s),
            "live_armed": live_armed, "live_filled": live_filled, "overlap": if new { "new" } else { "same" },
            "fill": fl.is_some(), "later_buy_sol_3": fl.as_ref().map(|f| f.lb), "later_buyers": fl.as_ref().map(|f| f.nbuy), "paper_sol": fl.as_ref().map(|f| f.paper),
            "eval": {"exec_slot": w.eval_slot, "slot_clock": w.clock, "t": w.t}, "complete": complete, "late_trades": late,
            "f": w.f.to_vec(), "model_sha": &self.m.sha[..16], "feat_hash": feat_hash(&w.f)});
        if let Some(f) = fl {
            r["dump"] = serde_json::json!({"slot": f.dump.slot, "i0": f.dump.i0, "i1": f.dump.i1, "drop": f.dump.drop, "sol": f.dump.sol, "spct": f.dump.spct});
            r["entry"] = serde_json::json!([f.es, f.ei]);
            r["exit_slot"] = (f.es + self.m.hold).into();
            r["dslot_fill"] = (f.dump.slot - w.s).into();
        }
        r
    }

    fn prune(&mut self) {
        let cur = self.cur;
        let lo = cur.saturating_sub(KEEP_SLOTS);
        self.toks.retain(|_, t| {
            while t.trades.len() > 1 && t.trades.front().is_some_and(|x| x.slot < lo) && t.open_w == 0 { t.trades.pop_front(); }
            t.live_arms.retain(|a| a.1 + LIVE_KEEP >= cur);
            t.live_fills.retain(|s| s + LIVE_KEEP >= cur);
            while t.big.front().is_some_and(|d| d.slot + 64 < cur) { t.big.pop_front(); }
            t.open_w > 0 || t.last_slot + IDLE_SLOTS >= cur || t.cslot.is_some_and(|c| c + IDLE_SLOTS >= cur)
        });
        while self.smax.len() > 256 { let k = *self.smax.keys().next().unwrap(); self.smax.remove(&k); }
        self.st.toks = self.toks.len() as u64;
    }

    /// our live (or dry) window armed [from, to] / filled at slot on the token
    pub fn live(&mut self, m: &Pk, stage: &str, slot: u64, en: Option<u64>) {
        let t = self.toks.entry(*m).or_default();
        match stage { "arm" => t.live_arms.push((slot, en.unwrap_or(slot + 23).max(slot))), "fill" => t.live_fills.push(slot), _ => {} }
    }

    pub fn status(&self) -> String {
        let s = &self.st;
        format!(" | B1 LOG: queries {} (dec>=0.2 {}, b0 {}, b1 {}) windows b1 {} (new {}, fills {}, paper {:+.3}) b0 {} (fills {}, paper {:+.3}) open {} late {}",
            s.queries, s.dec_pass, s.b0_pass, s.b1_pass, s.win_b1, s.new_b1, s.fills_b1, s.paper_b1, s.win_b0, s.fills_b0, s.paper_b0, self.wins.len(), s.late)
    }

    /// the run's end: every pending query scored, every window settled (complete: false when its time had not come)
    pub fn finish(&mut self, t: u64, clock: u64, flags: &dyn Fn(&Pk, u64) -> Flags, out: &mut Vec<serde_json::Value>) -> serde_json::Value {
        let dirty = std::mem::take(&mut self.dirty);
        for m in &dirty {
            let d = self.toks.get_mut(m).and_then(|t| t.close_run(self.m.drop));
            if let Some(d) = d { self.on_dump(m, d); }
        }
        for m in &dirty { self.query(m, t, clock, flags); }
        self.settle(true, out);
        let s = &self.st;
        serde_json::json!({"mode": "log", "model_sha": self.m.sha, "trades": s.trades, "creates": s.creates, "late": s.late, "queries": s.queries, "nonstd": s.nonstd,
            "dec_pass": s.dec_pass, "b0_pass": s.b0_pass, "b1_pass": s.b1_pass, "gate_rows": s.gate_rows, "windows_b0": s.win_b0, "windows_b1": s.win_b1, "fills_b0": s.fills_b0,
            "fills_b1": s.fills_b1, "paper_b0": s.paper_b0, "paper_b1": s.paper_b1, "windows_b1_new": s.new_b1, "fills_b1_new": s.fills_new_b1, "paper_b1_new": s.paper_new_b1,
            "max_eval_lag": s.max_lag, "tokens": self.toks.len()})
    }
}
