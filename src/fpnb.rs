//! dip36 FP-NOBOT (LOG-ONLY; owner OK 11-05 PKT): the frozen "no follower bot within 2 slots after our pre-sent fill" filter of the
//! flatperfect study (ops/strategies/presend/flatperfect/REPORT.md, FROZEN_FLAT.json; spec /home/moiz/sniper-data/flatperfect/ENGINE_SPEC.txt).
//! The pure part: the 6 frozen LightGBM models (embedded, sha256-checked), the 153 inputs in the frozen order, the chain store they are
//! computed from (per-mint trade rows and failed txs, the 30-min regime rings, the 24 h per-wallet whale history), our own results and
//! the shadow's row-c book, the hot-reloaded bot list and the preload file. The engine's glue (its own thread, the records) is
//! src/bin/snipe_engine/pslog36.rs. NOTHING here acts on a trade: it only scores.
//!   * score = mean over the kind's 3 seed models of sigmoid(sum of leaf values); would_block = covered && warm && score >= thr[kind]
//!   * inputs as fp1_chain.py / fp2_own.py (the reference when the spec is ambiguous); a send at slot t sees rows with slot <= t - 1
//!   * the bot list F / CORE: membership is checked at QUERY time over the stored raw events (a newly added wallet counts at once)
//!   * memory: every ring / map has a cap (see the constants); a mint that lost rows to a cap or a feed gap is "not covered" (never blocks)
use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::VecDeque;

pub type Pk = [u8; 32];

/// the frozen input order (model column k = FEATS[k]; spec section 6)
pub const FEATS: [&str; 153] = ["a_age", "a_crpct", "a_nb", "a_nb50", "a_pct", "a_sol", "a_vsol", "age", "age_cens", "bfail_pre", "bfail_pre_50", "bfail_pre_w",
    "bot_buy_50", "bot_hold_n", "bot_hold_pct", "bot_last_age", "bot_tr_n", "bot_w_n", "bsol_100", "bsol_20", "bsol_500", "buyers", "cre_is_whale", "dd_ath", "eq_n",
    "fail_all_pre", "g_bfail_1m", "g_bfail_20s", "g_bfail_30m", "g_bfail_5m", "g_botbuys_1m", "g_botbuys_20s", "g_botbuys_30m", "g_botbuys_5m", "g_botsonline_1m",
    "g_botsonline_30m", "g_botsonline_5m", "g_bsol_1m", "g_bsol_30m", "g_bsol_5m", "g_buys_1m", "g_buys_30m", "g_buys_5m", "g_core_5m", "g_core_last", "g_fol12_1m",
    "g_fol12_30m", "g_fol12_5m", "g_fol_1m", "g_fol_30m", "g_fol_5m", "g_nd_1m", "g_nd_30m", "g_nd_5m", "h_max", "h_n", "h_sum", "is_T2", "n_100", "n_20", "n_500",
    "n_h1", "n_h3", "n_prior", "nbuyer_100", "nbuyer_20", "nbuyer_500", "o_cr_n", "o_cr_sum", "o_flat10", "o_flat20", "o_flat40", "o_flat5", "o_flat_15m", "o_flat_60m",
    "o_fol10", "o_fol20", "o_fol40", "o_fol5", "o_lastwin_min", "o_mean10", "o_mean20", "o_mean40", "o_mean5", "o_n_15m", "o_n_60m", "o_sum_15m", "o_sum_60m", "o_tok_n",
    "o_tok_sum", "o_wh_n", "o_wh_sum", "o_win10", "o_win20", "o_win40", "o_win5", "o_win_15m", "o_win_60m", "pf_bfail", "pf_bfail_last3", "pf_bfail_w", "pf_bot_buys",
    "pf_bot_sells", "pf_bot_w", "pf_bsol", "pf_buyers", "pf_fail_all", "pf_last_gap", "pf_n", "pf_sellers", "pf_slots", "pf_ssol", "pf_vlast", "pf_vmax", "pf_vmin",
    "pf_wh_sold", "q_coh_hold", "q_fb_n", "q_since_last", "q_wh_dumps", "q_wh_fol", "s_arms_5m", "s_mean10", "s_mean30", "s_mean_15m", "s_n_15m", "s_pos10", "s_pos30",
    "sellers", "ssol_100", "ssol_20", "ssol_500", "t_hour", "tok_dump_fol", "tok_dumps", "top1", "top5", "trig_pct", "trig_sol", "v_dd120", "v_high", "v_n120", "v_ntr60",
    "vsol_max", "vsol_post", "vsol_pre", "wh_big", "wh_mints", "wh_n", "wh_prehold", "wh_q10", "wh_q50", "wh_sold_frac"];
pub const N_FEAT: usize = 153;
/// the per-send inputs (recomputed at every send slot t from data <= t - 1); everything else is fixed at the arm
pub const SEND_IX: [usize; 20] = [27, 31, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115];
/// the frozen thresholds (FROZEN_FLAT.json kinds.*.thr)
pub const THR_T2: f64 = 0.38795783438873316;
pub const THR_REARM: f64 = 0.5004509801610366;
pub const SUP: f64 = 1e15;
/// our two wallets (never in F; excluded where the spec says "ours")
pub const OURS_B58: [&str; 2] = ["EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"];
/// the regime windows (slots: "1m", "5m", "30m"; slot ~ 0.214 s)
pub const W_1M: u64 = 280;
pub const W_5M: u64 = 1400;
pub const W_30M: u64 = 8400;
/// the whale history look-back (the study's 24 h variant: dev_wh_403000)
pub const WH_LOOKBACK: u64 = 403_000;
/// seconds per slot (the study's clock: 280 slots = 1 min)
pub const SLOT_S: f64 = 60.0 / 280.0;
/// no flag (would_block) in the feed's first 30 min (spec FLAG 3)
pub const WARM_SLOTS: u64 = 8400;
/// a jump of the feed's slot clock bigger than this = a feed gap (every mint seen before it: not covered; the regime warms up again)
pub const GAP_SLOTS: u64 = 50;
/// a preload whose end is this far before the feed's start still counts as contiguous whale history (30 min)
pub const PRE_GAP_SLOTS: u64 = 8400;
/// caps (memory bounded)
pub const MINT_ROWS_CAP: usize = 40_000;
pub const MINT_FAILS_CAP: usize = 40_000;
pub const MINTS_CAP: usize = 300_000;
pub const MINT_IDLE_SLOTS: u64 = 33_600; // 2 h
pub const RING_CAP: usize = 3_000_000;
pub const DUMPS_CAP: usize = 200_000;
pub const WH_ROWS_CAP: usize = 25_000_000;
pub const OWN_CAP: usize = 4_000;
pub const SH_CAP: usize = 20_000;
const SWEEP_SLOTS: u64 = 2_000;
/// the embedded frozen models (LightGBM 4.7 text dumps; sha256 = FROZEN_FLAT.json)
pub const MODEL_TXT: [(&str, &str, &str); 6] = [
    ("T2", include_str!("fpnb_models/frozen_T2_s0.txt"), "92326b0242c4c99b3d358ba27d3d28a2ba75a85e0ee7f0d523b8084ff52e10da"),
    ("T2", include_str!("fpnb_models/frozen_T2_s1.txt"), "08b1be4ac3f70a57af18961334632b5b136fa2b4c52f712088b3939520bef564"),
    ("T2", include_str!("fpnb_models/frozen_T2_s2.txt"), "94ba2ce0995cda50a222bd876c0dd375653f2d1fbe20e6bde3dc1caf6c11d7b1"),
    ("rearm", include_str!("fpnb_models/frozen_rearm_s0.txt"), "edea8cefe0b174cb47f137504bf5b14c4da35e44d3ab3e921075521fc709db09"),
    ("rearm", include_str!("fpnb_models/frozen_rearm_s1.txt"), "449a5876da1d8664b758dfb8ff82757d2e2596fd0950939051ba9ac3cb199164"),
    ("rearm", include_str!("fpnb_models/frozen_rearm_s2.txt"), "9546b0c5595a604f4989389a3b77b27093f2862c72e321cbffe88500e6476f71"),
];

pub fn feat_ix(name: &str) -> usize {
    static IX: std::sync::OnceLock<FxHashMap<&'static str, usize>> = std::sync::OnceLock::new();
    *IX.get_or_init(|| FEATS.iter().enumerate().map(|(i, f)| (*f, i)).collect()).get(name).unwrap_or_else(|| panic!("fpnb: unknown input {name}"))
}

/// the 153 inputs (NaN = missing)
#[derive(Clone, Debug)]
pub struct X(pub [f64; N_FEAT]);
impl Default for X { fn default() -> X { X([f64::NAN; N_FEAT]) } }
impl X {
    pub fn set(&mut self, k: &str, v: f64) { self.0[feat_ix(k)] = v; }
    pub fn get(&self, k: &str) -> f64 { self.0[feat_ix(k)] }
    /// JSON: NaN -> null
    pub fn json(&self) -> serde_json::Value { nanj(&self.0) }
    pub fn send_json(&self) -> serde_json::Value { nanj(&SEND_IX.map(|i| self.0[i])) }
}
pub fn nanj(v: &[f64]) -> serde_json::Value {
    serde_json::Value::Array(v.iter().map(|x| if x.is_finite() { serde_json::json!(x) } else { serde_json::Value::Null }).collect())
}

// =====================================================================================================================
// THE MODELS: LightGBM text format, numerical splits only ("<=": left), missing types None (NaN -> 0.0) / Zero / NaN (default side)
// =====================================================================================================================
#[derive(Clone, Debug, Default)]
pub struct Tree { feat: Vec<usize>, thr: Vec<f64>, dl: Vec<bool>, mt: Vec<u8>, left: Vec<i32>, right: Vec<i32>, leaf: Vec<f64> }

impl Tree {
    pub fn eval(&self, x: &[f64]) -> f64 {
        if self.feat.is_empty() { return self.leaf[0]; }
        let mut n = 0usize;
        loop {
            let mut v = x[self.feat[n]];
            let mt = self.mt[n];
            if v.is_nan() && mt != 2 { v = 0.0; }
            let left = if (mt == 1 && v.abs() <= 1e-35) || (mt == 2 && v.is_nan()) { self.dl[n] } else { v <= self.thr[n] };
            let c = if left { self.left[n] } else { self.right[n] };
            if c < 0 { return self.leaf[(!c) as usize]; }
            n = c as usize;
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct Model { pub trees: Vec<Tree> }

impl Model {
    /// the LightGBM text model (exact f64 parsing of every number)
    pub fn parse(txt: &str) -> Result<Model, String> {
        if !txt.lines().any(|l| l.trim() == "objective=binary sigmoid:1") { return Err("not a binary sigmoid:1 model".into()); }
        if !txt.lines().any(|l| l.trim() == format!("max_feature_idx={}", N_FEAT - 1)) { return Err("max_feature_idx is not 152".into()); }
        let body = txt.split("end of trees").next().ok_or("no trees")?;
        let mut trees = Vec::new();
        for blk in body.split("\nTree=").skip(1) {
            let mut kv: FxHashMap<&str, &str> = FxHashMap::default();
            for l in blk.lines().skip(1) { if let Some((k, v)) = l.split_once('=') { kv.insert(k.trim(), v.trim()); } }
            let get = |k: &str| kv.get(k).copied().ok_or(format!("tree without {k}"));
            let nl: usize = get("num_leaves")?.parse().map_err(|e| format!("num_leaves: {e}"))?;
            if get("num_cat").unwrap_or("0") != "0" { return Err("categorical splits are not supported".into()); }
            let f64s = |k: &str| -> Result<Vec<f64>, String> { get(k)?.split_whitespace().map(|s| s.parse::<f64>().map_err(|e| format!("{k}: {e}"))).collect() };
            let i64s = |k: &str| -> Result<Vec<i64>, String> { get(k)?.split_whitespace().map(|s| s.parse::<i64>().map_err(|e| format!("{k}: {e}"))).collect() };
            let leaf = f64s("leaf_value")?;
            if leaf.len() != nl { return Err("leaf count".into()); }
            if nl == 1 { trees.push(Tree { leaf, ..Default::default() }); continue; }
            let feat: Vec<usize> = i64s("split_feature")?.into_iter().map(|v| v as usize).collect();
            let dt = i64s("decision_type")?;
            if dt.iter().any(|d| d & 1 != 0) { return Err("categorical decision".into()); }
            let t = Tree { thr: f64s("threshold")?, dl: dt.iter().map(|d| d & 2 != 0).collect(), mt: dt.iter().map(|d| ((d >> 2) & 3) as u8).collect(),
                left: i64s("left_child")?.into_iter().map(|v| v as i32).collect(), right: i64s("right_child")?.into_iter().map(|v| v as i32).collect(), feat, leaf };
            if [t.thr.len(), t.dl.len(), t.left.len(), t.right.len()].iter().any(|&n| n != nl - 1) || t.feat.iter().any(|&f| f >= N_FEAT) { return Err("bad tree shape".into()); }
            trees.push(t);
        }
        if trees.is_empty() { return Err("no trees".into()); }
        Ok(Model { trees })
    }
    pub fn raw(&self, x: &[f64]) -> f64 { self.trees.iter().map(|t| t.eval(x)).sum() }
    pub fn p(&self, x: &[f64]) -> f64 { 1.0 / (1.0 + (-self.raw(x)).exp()) }
}

/// both kinds' 3 seeds
#[derive(Clone, Debug)]
pub struct Models { pub t2: [Model; 3], pub rearm: [Model; 3] }

/// a score: the seeds' probabilities and their mean
#[derive(Clone, Debug, PartialEq)]
pub struct Score { pub seeds: [f64; 3], pub score: f64, pub thr: f64 }

impl Models {
    /// the embedded models, each checked against its frozen sha256
    pub fn frozen() -> Result<Models, String> {
        use sha2::Digest;
        let mut v: Vec<Model> = Vec::new();
        for (k, txt, sha) in MODEL_TXT {
            let h = sha2::Sha256::digest(txt.as_bytes()).iter().map(|b| format!("{b:02x}")).collect::<String>();
            if h != sha { return Err(format!("fpnb {k} model sha256 {h} != frozen {sha}")); }
            v.push(Model::parse(txt)?);
        }
        let mut it = v.into_iter();
        let mut n = || it.next().unwrap();
        Ok(Models { t2: [n(), n(), n()], rearm: [n(), n(), n()] })
    }
    pub fn score(&self, t2: bool, x: &X) -> Score {
        let m = if t2 { &self.t2 } else { &self.rearm };
        let seeds = [m[0].p(&x.0), m[1].p(&x.0), m[2].p(&x.0)];
        Score { seeds, score: (seeds[0] + seeds[1] + seeds[2]) / 3.0, thr: if t2 { THR_T2 } else { THR_REARM } }
    }
}

// =====================================================================================================================
// THE BOT LIST (F) and CORE: an external file, hot-reloaded by the glue. Accepted shapes (first match):
//   {"engine_view" | "engine view" | "engineView": [ "addr", ... ] | [ {wallet|address|addr|w|pubkey, operator|op|operator_id|opid, active?}, ... ]
//                                                  | {"wallets": [ same ]}}
//   {"cohort": [addr...], "named": [addr...]}       (v0: cohort_full_b58.json; named operators from the seed map below)
//   [ addr | {...} , ... ]
// "version" | "ver" | "v" (any) is logged. An entry with "active": false is left out. Our wallets are never members. An empty list or any
// bad address = a failed load (the last good list stays).
// =====================================================================================================================
pub const CORE_OPS: [&str; 3] = ["haqq", "9pQQ", "8PgC"];
/// the v0 named wallets' operator ids (flatsig flib.NAMED); a cohort-only wallet's id is its own address
pub const NAMED_OPS: [(&str, &str); 26] = [
    ("haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq", "haqq"), ("haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "haqq"), ("2VggYpPumR3sV4K9vBqDzsmKzpB3BgSM4woRwbqqzweg", "haqq"),
    ("9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN", "9pQQ"), ("8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk", "8PgC"), ("8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3", "8yYM"),
    ("E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb", "E2x1"), ("EMKY7r6UekmmR1hREwCaPy835tCDGXGCw8fqibybgqzc", "EMKY"), ("sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d", "sssss"),
    ("ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssss"), ("sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ", "sssss"), ("sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssss"),
    ("4ggJqUDDHB9uZMSyR485VgYLMGLotV7Ctm9NDURCpp6f", "4ggJ"), ("DL7cmioGVA7Y4QLnhGZN1zrcNYhqnGzZcrGec3WJJS7d", "DL7c"), ("6Z91Dgiz9E44bMW11rQuMBjt1NwwPoQGXFNZieGfVtAb", "6Z91"),
    ("5ZtzVYRuF7sEhot31S68xHRCKDMkDdFtTp1iujTRjowV", "5Ztz"), ("3qvuM3U5UZPVagL1spxmgVgUvzT3h49gyJZyagxRtqKr", "3qvu"), ("BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP", "BUkp"),
    ("Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ", "Groz"), ("EUkuD2J2KPcsbEFcSdm7SnkEXw6vAXr6XVB5FhFoziAo", "EUku"), ("HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "HkQ7"),
    ("DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9", "DF7e"), ("CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx", "CZ77"), ("6VzXcLk9rCLDHgRBmUGKK8HY2KvhHmR4pZPCxi4tA1kx", "6VzX"),
    ("ETwEAQPLnAMRbU9EXjXTYoq8msfLkaD8x1AD1Zcbnz6b", "ETwE"), ("DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "DYXD"),
];

pub fn pk(s: &str) -> Option<Pk> { bs58::decode(s.trim()).into_vec().ok().and_then(|v| v.try_into().ok()) }
pub fn b58(k: &Pk) -> String { bs58::encode(k).into_string() }
pub fn ours() -> Vec<Pk> { OURS_B58.iter().filter_map(|s| pk(s)).collect() }
/// the first 8 bytes of a pubkey, big-endian (the study's mint id / sort key)
pub fn pk64(k: &Pk) -> u64 { u64::from_be_bytes(k[..8].try_into().unwrap()) }

#[derive(Clone, Debug, Default)]
pub struct BotList { pub set: FxHashSet<Pk>, pub core: FxHashSet<Pk>, pub ops: FxHashMap<Pk, String>, pub ver: String, pub sha8: String, pub n: usize, pub n_ops: usize }

impl BotList {
    pub fn is_f(&self, w: &Pk) -> bool { self.set.contains(w) }
    pub fn is_core(&self, w: &Pk) -> bool { self.core.contains(w) }
    pub fn meta(&self) -> serde_json::Value { serde_json::json!({"ver": self.ver, "sha8": self.sha8, "n": self.n, "core": self.core.len(), "ops": self.n_ops}) }

    pub fn parse(bytes: &[u8], ours: &[Pk]) -> Result<BotList, String> {
        use sha2::Digest;
        let v: serde_json::Value = serde_json::from_slice(bytes).map_err(|e| format!("bad JSON: {e}"))?;
        let mut ent: Vec<(String, Option<String>)> = Vec::new();
        let mut take = |a: &serde_json::Value| -> Result<(), String> {
            let a = if let Some(w) = a.get("wallets") { w } else { a };
            for e in a.as_array().ok_or("the list is not an array")? {
                if let Some(s) = e.as_str() { ent.push((s.to_string(), None)); continue; }
                if e.get("active").and_then(|x| x.as_bool()) == Some(false) { continue; }
                let w = ["wallet", "address", "addr", "w", "pubkey"].iter().find_map(|k| e.get(*k).and_then(|x| x.as_str())).ok_or(format!("an entry without an address: {e}"))?;
                let op = ["operator", "op", "operator_id", "opid"].iter().find_map(|k| e.get(*k).and_then(|x| x.as_str())).map(|s| s.to_string());
                ent.push((w.to_string(), op));
            }
            Ok(())
        };
        if let Some(a) = ["engine_view", "engine view", "engineView"].iter().find_map(|k| v.get(*k)) { take(a)?; }
        else if v.get("cohort").is_some() || v.get("named").is_some() {
            for k in ["cohort", "named"] { if let Some(a) = v.get(k) { take(a)?; } }
        } else if v.is_array() { take(&v)?; } else { return Err("no engine_view / cohort+named / list".into()); }
        let seed: FxHashMap<&str, &str> = NAMED_OPS.iter().copied().collect();
        let mut l = BotList::default();
        for (s, op) in ent {
            let k = pk(&s).ok_or(format!("bad address {s}"))?;
            if ours.contains(&k) { continue; }
            let op = op.or_else(|| seed.get(s.trim()).map(|x| x.to_string())).unwrap_or_else(|| s.trim().to_string());
            if CORE_OPS.contains(&op.as_str()) { l.core.insert(k); }
            l.set.insert(k);
            l.ops.insert(k, op);
        }
        if l.set.is_empty() { return Err("an empty list".into()); }
        l.n = l.set.len();
        l.n_ops = l.ops.values().collect::<FxHashSet<_>>().len();
        l.ver = ["version", "ver", "v"].iter().find_map(|k| v.get(*k)).map(|x| x.as_str().map(|s| s.to_string()).unwrap_or_else(|| x.to_string())).unwrap_or_else(|| "-".into());
        l.sha8 = sha2::Sha256::digest(bytes).iter().take(4).map(|b| format!("{b:02x}")).collect();
        Ok(l)
    }
}

// =====================================================================================================================
// THE CHAIN STORE
// =====================================================================================================================
/// one pump.fun TradeEvent of a successful tx (chain order = (s, i, j))
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Row { pub s: u64, pub i: u32, pub j: i32, pub buy: bool, pub user: Pk, pub sol: u64, pub tok: u64, pub vsol: u64 }
impl Row { fn key(&self) -> (u64, u32, i32) { (self.s, self.i, self.j) } }

/// one failed tx touching a tracked mint whose logs name a Buy* / Sell* instruction (`buy` = BUY kind)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Fail { pub s: u64, pub i: u32, pub payer: Pk, pub buy: bool }

#[derive(Clone, Debug, Default)]
struct MintSt { rows: Vec<Row>, fails: Vec<Fail>, created: bool, complete: bool, fails_complete: bool, epoch: u32, last: u64 }

#[derive(Clone, Copy, Debug)]
struct GTr { s: u64, user: Pk, buy: bool, ours: bool }
#[derive(Clone, Copy, Debug)]
struct GFail { s: u64, payer: Pk, buy: bool }
#[derive(Clone, Copy, Debug)]
struct Dump { s: u64, i: u32, j: i32, mint: Pk, drop: f64 }
/// a whale-history row: mint id (pk64), slot, flags (1 = buy, 2 = big: >= 6% of supply)
#[derive(Clone, Copy, Debug)]
pub struct WRow { pub m: u64, pub s: u32, pub f: u8 }

fn drop_of(r: &Row) -> f64 {
    let vs = r.vsol as f64;
    let vb = if r.buy { vs - r.sol as f64 } else { vs + r.sol as f64 };
    if !r.buy && vb > 0.0 { 1.0 - (vs / vb.max(1.0)).powi(2) } else { 0.0 }
}
fn is_dump(r: &Row) -> bool { !r.buy && drop_of(r) >= 0.10 && r.sol as f64 >= 0.5e9 }

/// counters (the run's end / status)
#[derive(Clone, Debug, Default, serde::Serialize)]
pub struct StoreStats { pub rows: u64, pub dup_rows: u64, pub fails: u64, pub fails_untracked: u64, pub dup_fails: u64, pub gaps: u64, pub truncated: u64, pub evicted: u64,
    pub wh_rows: usize, pub wh_wallets: usize, pub mints: usize, pub ring: usize, pub fail_ring: usize, pub dumps: usize }

/// the preload's whale-history span
#[derive(Clone, Copy, Debug, Default)]
pub struct PreSpan { pub from: u64, pub to: u64 }

pub struct Store {
    pub ours: Vec<Pk>,
    mints: FxHashMap<Pk, MintSt>,
    g_tr: VecDeque<GTr>,
    g_fail: VecDeque<GFail>,
    dumps: VecDeque<Dump>,
    wh: FxHashMap<Pk, Vec<WRow>>,
    wh_n: usize,
    pub pre: Option<PreSpan>,
    /// the feed's first slot (after the last gap) / newest slot / epoch (a gap = a new epoch)
    pub start: u64,
    /// the very first slot (whale history coverage when there is no preload)
    pub first: u64,
    pub max: u64,
    pub epoch: u32,
    last_sweep: u64,
    pub gap_slots: u64,
    /// the whale history's look-back and the coverage it needs before its inputs count (both WH_LOOKBACK; the parity test widens them)
    pub wh_lookback: u64,
    pub wh_need: u64,
    /// the housekeeping period (slots; the parity test turns it off)
    pub sweep_slots: u64,
    /// the feed uptime before any block (WARM_SLOTS; the gate's tests set 0)
    pub warm_slots: u64,
    pub st: StoreStats,
}

impl Store {
    pub fn new(ours: Vec<Pk>) -> Store {
        Store { ours, mints: FxHashMap::default(), g_tr: VecDeque::new(), g_fail: VecDeque::new(), dumps: VecDeque::new(), wh: FxHashMap::default(), wh_n: 0, pre: None,
            start: 0, first: 0, max: 0, epoch: 0, last_sweep: 0, gap_slots: GAP_SLOTS, wh_lookback: WH_LOOKBACK, wh_need: WH_LOOKBACK, sweep_slots: SWEEP_SLOTS, warm_slots: WARM_SLOTS, st: StoreStats::default() }
    }
    fn is_ours(&self, w: &Pk) -> bool { self.ours.contains(w) }

    fn clock(&mut self, s: u64) {
        if self.start == 0 { self.start = s; self.first = s; self.max = s; self.last_sweep = s; return; }
        if s > self.max + self.gap_slots {
            // a feed gap: a new epoch (every mint seen before: not covered), the regime warms up again
            self.st.gaps += 1;
            self.epoch += 1;
            self.start = s;
        }
        if s > self.max { self.max = s; }
        if self.max >= self.last_sweep.saturating_add(self.sweep_slots) { self.sweep(); }
    }

    /// a create (the token's history starts here: age_cens 0)
    pub fn create(&mut self, mint: Pk, s: u64) {
        self.clock(s);
        let ep = self.epoch;
        let m = self.mints.entry(mint).or_insert_with(|| MintSt { complete: true, fails_complete: true, epoch: ep, ..Default::default() });
        if m.rows.is_empty() { m.created = true; }
        m.last = m.last.max(s);
    }

    /// a trade row (any order; duplicates of (s, i, j) dropped)
    pub fn trade(&mut self, mint: Pk, r: Row) {
        self.clock(r.s);
        let ep = self.epoch;
        let ours = self.is_ours(&r.user);
        let m = self.mints.entry(mint).or_insert_with(|| MintSt { complete: true, fails_complete: true, epoch: ep, ..Default::default() });
        let k = r.key();
        let at = if m.rows.last().is_none_or(|x| x.key() < k) { m.rows.len() } else {
            let p = m.rows.partition_point(|x| x.key() < k);
            if m.rows.get(p).is_some_and(|x| x.key() == k) { self.st.dup_rows += 1; return; }
            p
        };
        m.rows.insert(at, r);
        m.last = m.last.max(r.s);
        if m.rows.len() > MINT_ROWS_CAP { m.rows.drain(..MINT_ROWS_CAP / 2); m.complete = false; self.st.truncated += 1; }
        self.st.rows += 1;
        if self.g_tr.len() >= RING_CAP { self.g_tr.pop_front(); }
        self.g_tr.push_back(GTr { s: r.s, user: r.user, buy: r.buy, ours });
        if is_dump(&r) && !ours {
            if self.dumps.len() >= DUMPS_CAP { self.dumps.pop_front(); }
            self.dumps.push_back(Dump { s: r.s, i: r.i, j: r.j, mint, drop: drop_of(&r) });
        }
        // whale history (rows the preload already holds are not added twice)
        if self.pre.is_none_or(|p| r.s > p.to) {
            let f = (r.buy as u8) | if r.buy && r.tok as f64 >= 0.06 * SUP { 2 } else { 0 };
            self.wh.entry(r.user).or_default().push(WRow { m: pk64(&mint), s: r.s as u32, f });
            self.wh_n += 1;
        }
    }

    /// a failed tx (payer, BUY / SELL, its account keys): kept on the first TRACKED mint among the keys; false: no tracked mint (dropped)
    pub fn fail(&mut self, s: u64, i: u32, payer: Pk, buy: bool, keys: &[Pk]) -> bool {
        let Some(mint) = keys.iter().find(|k| self.mints.contains_key(*k)).copied() else { self.st.fails_untracked += 1; return false };
        self.clock(s);
        let m = self.mints.get_mut(&mint).unwrap();
        let f = Fail { s, i, payer, buy };
        let k = (s, i);
        let at = if m.fails.last().is_none_or(|x| (x.s, x.i) < k) { m.fails.len() } else {
            let p = m.fails.partition_point(|x| (x.s, x.i) < k);
            if m.fails.get(p).is_some_and(|x| (x.s, x.i) == k) { self.st.dup_fails += 1; return true; }
            p
        };
        m.fails.insert(at, f);
        if m.fails.len() > MINT_FAILS_CAP { m.fails.drain(..MINT_FAILS_CAP / 2); m.fails_complete = false; self.st.truncated += 1; }
        self.st.fails += 1;
        if self.g_fail.len() >= RING_CAP { self.g_fail.pop_front(); }
        self.g_fail.push_back(GFail { s, payer, buy });
        true
    }

    pub fn tracked(&self, mint: &Pk) -> bool { self.mints.contains_key(mint) }

    /// the mint's rows with first < (slot, idx) <= last (a position's hold: its follower count)
    pub fn rows_between(&self, mint: &Pk, first: (u64, u64), last: (u64, u64)) -> Vec<Row> {
        self.mints.get(mint).map(|m| m.rows.iter().filter(|r| (r.s, r.i as u64) > first && (r.s, r.i as u64) <= last).copied().collect()).unwrap_or_default()
    }

    /// whale-history rows from the preload (wallet, mint id, slot, flags) and its span
    pub fn preload_wh(&mut self, rows: impl IntoIterator<Item = (Pk, WRow)>, span: PreSpan) {
        for (w, r) in rows { self.wh.entry(w).or_default().push(r); self.wh_n += 1; }
        for v in self.wh.values_mut() { v.sort_by_key(|r| r.s); }
        self.pre = Some(span);
    }

    /// the slot the whale history covers from (the preload's start when it reaches the feed's first slot within 30 min)
    pub fn wh_from(&self) -> u64 {
        match self.pre { Some(p) if self.first == 0 || p.to + PRE_GAP_SLOTS >= self.first => p.from, _ => self.first }
    }

    fn sweep(&mut self) {
        self.last_sweep = self.max;
        let max = self.max;
        let n0 = self.mints.len();
        self.mints.retain(|_, m| m.last + MINT_IDLE_SLOTS >= max);
        if self.mints.len() > MINTS_CAP {
            let mut l: Vec<u64> = self.mints.values().map(|m| m.last).collect();
            l.sort_unstable();
            let cut = l[self.mints.len() - MINTS_CAP];
            self.mints.retain(|_, m| m.last > cut);
        }
        self.st.evicted += (n0 - self.mints.len()) as u64;
        let lo = max.saturating_sub(W_30M + 200);
        while self.g_tr.front().is_some_and(|x| x.s < lo) { self.g_tr.pop_front(); }
        while self.g_fail.front().is_some_and(|x| x.s < lo) { self.g_fail.pop_front(); }
        while self.dumps.front().is_some_and(|x| x.s < lo) { self.dumps.pop_front(); }
        let mut wlo = max.saturating_sub(self.wh_lookback.saturating_add(2000));
        if self.wh_n > WH_ROWS_CAP { wlo = max.saturating_sub(self.wh_lookback / 2); if let Some(p) = self.pre.as_mut() { p.from = p.from.max(wlo); } self.first = self.first.max(wlo); }
        let mut n = 0;
        self.wh.retain(|_, v| { v.retain(|r| r.s as u64 >= wlo); n += v.len(); !v.is_empty() });
        self.wh_n = n;
    }

    pub fn stats(&self) -> StoreStats {
        let mut s = self.st.clone();
        s.wh_rows = self.wh_n; s.wh_wallets = self.wh.len(); s.mints = self.mints.len(); s.ring = self.g_tr.len(); s.fail_ring = self.g_fail.len(); s.dumps = self.dumps.len();
        s
    }

    /// followed / fsol of a dump: F BUY rows (fsol: every non-our buy) on its mint after it in chain order with slot <= dump + 2; `before`:
    /// only rows strictly before this key (tok_dump_fol)
    fn dump_follow(&self, mint: &Pk, d: (u64, u32, i32), before: Option<(u64, u32, i32)>, bots: &BotList) -> (bool, f64) {
        let Some(m) = self.mints.get(mint) else { return (false, 0.0) };
        let p = m.rows.partition_point(|x| x.key() <= d);
        let (mut fol, mut fsol) = (false, 0.0f64);
        for r in &m.rows[p..] {
            if r.s > d.0 + 2 || before.is_some_and(|b| r.key() >= b) { break; }
            if r.buy && !self.is_ours(&r.user) { fsol += r.sol as f64; if bots.is_f(&r.user) { fol = true; } }
        }
        (fol, fsol / 1e9)
    }
}

// =====================================================================================================================
// ARM / SEND inputs (spec sections 2, 3)
// =====================================================================================================================
/// what an arm needs (T2: the whale's buy; re-arm: the dump)
#[derive(Clone, Debug)]
pub struct ArmIn { pub t2: bool, pub mint: Pk, pub s: u64, pub i: u32, pub whale: Pk }

/// the arm's fixed state for its sends
#[derive(Clone, Debug)]
pub struct ArmCtx {
    pub x: X,
    pub t2: bool, pub mint: Pk, pub s: u64, pub whale: Pk,
    /// the trigger row's key and vsol (None: the trigger row is not in the store)
    pub r: Option<((u64, u32, i32), u64)>,
    pub epoch: u32,
    /// None = covered; else why not
    pub nc: Option<&'static str>,
    pub warm: bool,
    pub hist_h: f64,
    pub wh_ok: bool,
}

fn mean(v: &[f64]) -> f64 { v.iter().sum::<f64>() / v.len() as f64 }

impl Store {
    /// the chain part of the ARM inputs at the trigger row (sections 2); the send part is computed by `send`
    pub fn arm_chain(&self, a: &ArmIn, bots: &BotList, x: &mut X) -> ArmCtx {
        let s = a.s;
        let mut ctx = ArmCtx { x: X::default(), t2: a.t2, mint: a.mint, s, whale: a.whale, r: None, epoch: self.epoch, nc: None, warm: s >= self.start + self.warm_slots, hist_h: 0.0, wh_ok: false };
        x.set("is_T2", if a.t2 { 1.0 } else { 0.0 });
        self.regime(s, bots, x);
        self.whale_hist(&a.whale, s, &a.mint, x, &mut ctx);
        let Some(m) = self.mints.get(&a.mint) else { ctx.nc = Some("mint_not_seen"); return ctx };
        let p = m.rows.partition_point(|r| (r.s, r.i) < (s, a.i));
        let Some(r) = m.rows.get(p).filter(|r| (r.s, r.i) == (s, a.i)).copied() else { ctx.nc = Some("trigger_not_seen"); return ctx };
        ctx.r = Some((r.key(), r.vsol));
        if !m.complete || m.epoch != self.epoch { ctx.nc = Some(if m.complete { "feed_gap" } else { "history_truncated" }); }
        let pr = &m.rows[..p];
        let first = m.rows[0];
        x.set("age", (s - first.s) as f64);
        let cens = !m.created || first.s <= self.start + 2 || m.epoch != self.epoch;
        x.set("age_cens", if cens { 1.0 } else { 0.0 });
        x.set("n_prior", pr.len() as f64);
        let users = |f: &dyn Fn(&Row) -> bool| pr.iter().filter(|r| f(r)).map(|r| r.user).collect::<FxHashSet<Pk>>().len() as f64;
        x.set("buyers", users(&|r| r.buy));
        x.set("sellers", users(&|r| !r.buy));
        for w in [20u64, 100, 500] {
            let lo = s.saturating_sub(w);
            let inw = |r: &Row| r.s >= lo;
            x.set(&format!("n_{w}"), pr.iter().filter(|r| inw(r)).count() as f64);
            x.set(&format!("bsol_{w}"), pr.iter().filter(|r| inw(r) && r.buy).map(|r| r.sol as f64).sum::<f64>() / 1e9);
            x.set(&format!("ssol_{w}"), pr.iter().filter(|r| inw(r) && !r.buy).map(|r| r.sol as f64).sum::<f64>() / 1e9);
            x.set(&format!("nbuyer_{w}"), users(&|r| inw(r) && r.buy));
        }
        let vpre = if r.buy { r.vsol as f64 - r.sol as f64 } else { r.vsol as f64 + r.sol as f64 };
        x.set("vsol_pre", vpre / 1e9);
        x.set("vsol_post", r.vsol as f64 / 1e9);
        let vmax = if pr.is_empty() { vpre / 1e9 } else { pr.iter().map(|r| r.vsol).max().unwrap() as f64 / 1e9 };
        x.set("vsol_max", vmax);
        x.set("dd_ath", if vmax > 0.0 { 1.0 - (vpre / 1e9 / vmax).powi(2) } else { 0.0 });
        x.set("trig_pct", r.tok as f64 / SUP * 100.0);
        x.set("trig_sol", r.sol as f64 / 1e9);
        // holdings over the prior rows (% of supply; every wallet), in first-appearance order like np.unique's sorted ids (order-free sums)
        if pr.is_empty() {
            for k in ["top1", "top5", "n_h3", "n_h1", "bot_hold_n", "bot_hold_pct", "eq_n", "wh_prehold"] { x.set(k, 0.0); }
        } else {
            let mut hm: FxHashMap<Pk, f64> = FxHashMap::default();
            for r in pr { *hm.entry(r.user).or_default() += if r.buy { r.tok as f64 } else { -(r.tok as f64) }; }
            let hold: Vec<(Pk, f64)> = hm.into_iter().map(|(k, v)| (k, v / SUP * 100.0)).collect();
            let mut hs: Vec<f64> = hold.iter().filter(|(k, _)| *k != a.whale).map(|(_, v)| *v).collect();
            hs.sort_by(|a, b| b.total_cmp(a));
            x.set("top1", hs.first().copied().unwrap_or(0.0));
            x.set("top5", hs.iter().take(5).sum::<f64>());
            x.set("n_h3", hs.iter().filter(|v| **v >= 3.0).count() as f64);
            x.set("n_h1", hs.iter().filter(|v| **v >= 1.0).count() as f64);
            x.set("bot_hold_n", hold.iter().filter(|(k, v)| bots.is_f(k) && *v > 0.05).count() as f64);
            x.set("bot_hold_pct", hold.iter().filter(|(k, v)| bots.is_f(k) && *v > 0.0).map(|(_, v)| *v).sum::<f64>());
            let mut h1: Vec<f64> = hold.iter().map(|(_, v)| *v).filter(|v| *v >= 1.0).collect();
            h1.sort_by(|a, b| a.total_cmp(b));
            x.set("eq_n", if h1.len() > 1 { h1.windows(2).filter(|p| (p[1] - p[0]).abs() / p[1].max(1e-9) < 0.02).count() as f64 } else { 0.0 });
            x.set("wh_prehold", hold.iter().find(|(k, _)| *k == a.whale).map_or(0.0, |(_, v)| *v));
        }
        let isf = |u: &Pk| bots.is_f(u) && !self.is_ours(u);
        let fb: Vec<&Row> = pr.iter().filter(|r| isf(&r.user)).collect();
        x.set("bot_tr_n", fb.len() as f64);
        x.set("bot_w_n", fb.iter().map(|r| r.user).collect::<FxHashSet<Pk>>().len() as f64);
        x.set("bot_last_age", fb.iter().map(|r| r.s).max().map_or(99999.0, |m| (s - m) as f64));
        x.set("bot_buy_50", fb.iter().filter(|r| r.buy && r.s + 50 >= s).count() as f64);
        let dd: Vec<&Row> = pr.iter().filter(|r| is_dump(r)).collect();
        x.set("tok_dumps", dd.len() as f64);
        x.set("tok_dump_fol", if dd.is_empty() { f64::NAN } else {
            dd.iter().filter(|d| self.dump_follow(&a.mint, d.key(), Some(r.key()), bots).0).count() as f64 / dd.len() as f64
        });
        // failed txs on this mint before r
        let pre = |f: &Fail| f.s < s || (f.s == s && f.i < r.i);
        let bf: Vec<&Fail> = m.fails.iter().filter(|f| pre(f) && f.buy && bots.is_f(&f.payer)).collect();
        x.set("bfail_pre", bf.len() as f64);
        x.set("bfail_pre_w", bf.iter().map(|f| f.payer).collect::<FxHashSet<Pk>>().len() as f64);
        x.set("bfail_pre_50", bf.iter().filter(|f| f.s + 50 >= s).count() as f64);
        x.set("fail_all_pre", m.fails.iter().filter(|f| pre(f)).count() as f64);
        x.set("cre_is_whale", if !cens && first.user == a.whale { 1.0 } else { 0.0 });
        ctx
    }

    /// the regime inputs at slot s (chain-wide): NaN while the window is not fully inside the feed's history
    fn regime(&self, s: u64, bots: &BotList, x: &mut X) {
        let ws = [(W_1M, "1m"), (W_5M, "5m"), (W_30M, "30m")];
        let cov = |w: u64| s >= self.start + w;
        // dumps with slot in [s - W, s - 3]
        let mut dl: Vec<(u64, bool, f64, bool)> = Vec::new();
        for d in self.dumps.iter().filter(|d| d.s + W_30M >= s && d.s + 3 <= s) {
            let (fol, fsol) = self.dump_follow(&d.mint, (d.s, d.i, d.j), None, bots);
            dl.push((d.s, fol, fsol, d.drop >= 0.12));
        }
        let mut buys = [0u64; 3]; let mut bb = [0u64; 3]; let mut bf = [0u64; 3];
        let mut on: [FxHashSet<Pk>; 3] = Default::default();
        let (mut core_last, mut core5) = (0u64, 0u64);
        let lo = s.saturating_sub(W_30M);
        for g in self.g_tr.iter().filter(|g| g.s >= lo && g.s < s) {
            let f = bots.is_f(&g.user) && !g.ours;
            for (k, (w, _)) in ws.iter().enumerate() {
                if g.s + w < s { continue; }
                if g.buy && !g.ours { buys[k] += 1; }
                if f { on[k].insert(g.user); if g.buy { bb[k] += 1; } }
            }
            if bots.is_core(&g.user) { core_last = core_last.max(g.s); if g.s + W_5M >= s { core5 += 1; } }
        }
        for g in self.g_fail.iter().filter(|g| g.s >= lo && g.s < s) {
            let f = g.buy && bots.is_f(&g.payer);
            for (k, (w, _)) in ws.iter().enumerate() {
                if g.s + w < s { continue; }
                if f { bf[k] += 1; on[k].insert(g.payer); }
            }
            if bots.is_core(&g.payer) { core_last = core_last.max(g.s); if g.s + W_5M >= s { core5 += 1; } }
        }
        for (k, (w, nm)) in ws.iter().enumerate() {
            let set = |x: &mut X, key: &str, v: f64| x.set(&format!("{key}_{nm}"), if cov(*w) { v } else { f64::NAN });
            let ds: Vec<&(u64, bool, f64, bool)> = dl.iter().filter(|d| d.0 + w >= s).collect();
            let nd = ds.len() as f64;
            set(x, "g_nd", nd);
            set(x, "g_fol", if ds.is_empty() { f64::NAN } else { ds.iter().filter(|d| d.1).count() as f64 / nd });
            set(x, "g_bsol", if ds.is_empty() { f64::NAN } else { ds.iter().map(|d| d.2).sum::<f64>() / nd });
            let d12: Vec<&&(u64, bool, f64, bool)> = ds.iter().filter(|d| d.3).collect();
            set(x, "g_fol12", if d12.is_empty() { f64::NAN } else { d12.iter().filter(|d| d.1).count() as f64 / d12.len() as f64 });
            set(x, "g_botbuys", bb[k] as f64);
            set(x, "g_buys", buys[k] as f64);
            set(x, "g_bfail", bf[k] as f64);
            set(x, "g_botsonline", on[k].len() as f64);
        }
        x.set("g_core_5m", if cov(W_5M) { core5 as f64 } else { f64::NAN });
        x.set("g_core_last", if core_last > 0 { (s - core_last) as f64 } else if cov(W_30M) { 99999.0 } else { f64::NAN });
    }

    /// the whale's history (rows on any mint with slot in [s - WH_LOOKBACK, s)); NaN until the history covers the look-back (FLAG 1)
    fn whale_hist(&self, whale: &Pk, s: u64, mint: &Pk, x: &mut X, ctx: &mut ArmCtx) {
        let from = self.wh_from();
        ctx.hist_h = if from == 0 || from > s { 0.0 } else { (s - from) as f64 * SLOT_S / 3600.0 };
        ctx.wh_ok = from > 0 && s >= from.saturating_add(self.wh_need);
        if !ctx.wh_ok { return; }
        let m64 = pk64(mint);
        let lo = s.saturating_sub(self.wh_lookback);
        let rows: Vec<WRow> = self.wh.get(whale).map(|v| v.iter().filter(|r| (r.s as u64) < s && r.s as u64 >= lo).copied().collect()).unwrap_or_default();
        x.set("wh_n", rows.len() as f64);
        x.set("wh_mints", rows.iter().map(|r| r.m).collect::<FxHashSet<u64>>().len() as f64);
        x.set("wh_big", rows.iter().filter(|r| r.f & 3 == 3 && r.m != m64).count() as f64);
        let mut fb: FxHashMap<u64, u32> = FxHashMap::default();
        for r in rows.iter().filter(|r| r.f & 1 == 1 && r.m != m64) { let e = fb.entry(r.m).or_insert(u32::MAX); *e = (*e).min(r.s); }
        let mut ks: Vec<u64> = fb.keys().copied().collect();
        ks.sort_unstable();
        ks.truncate(400);
        let keep: FxHashSet<u64> = ks.iter().copied().collect();
        let mut fs: FxHashMap<u64, u32> = FxHashMap::default();
        for r in rows.iter().filter(|r| r.f & 1 == 0 && keep.contains(&r.m)) {
            if r.s >= fb[&r.m] { let e = fs.entry(r.m).or_insert(u32::MAX); *e = (*e).min(r.s); }
        }
        let nb = ks.len();
        let holds: Vec<f64> = ks.iter().filter_map(|m| fs.get(m).map(|e| (*e - fb[m]) as f64)).collect();
        if nb > 0 {
            x.set("wh_sold_frac", holds.len() as f64 / nb as f64);
            if !holds.is_empty() {
                x.set("wh_q10", holds.iter().filter(|h| **h <= 10.0).count() as f64 / holds.len() as f64);
                x.set("wh_q50", holds.iter().filter(|h| **h <= 50.0).count() as f64 / holds.len() as f64);
            }
        }
    }

    /// is the arm still covered at send slot t (the mint's history intact and no feed gap since the arm)
    pub fn covered(&self, c: &ArmCtx) -> Option<&'static str> {
        if let Some(w) = c.nc { return Some(w); }
        let Some(m) = self.mints.get(&c.mint) else { return Some("mint_evicted") };
        if !m.complete { return Some("history_truncated"); }
        if m.epoch != self.epoch || c.epoch != self.epoch { return Some("feed_gap"); }
        None
    }

    /// the 20 SEND inputs at send slot t (data with slot <= t - 1), into x
    pub fn send(&self, c: &ArmCtx, t: u64, bots: &BotList, x: &mut X) {
        let s = c.s;
        x.set("pf_slots", (t + 1) as f64 - s as f64);
        let tl = t.saturating_sub(1);
        let (mut gbf, mut gbb) = (0u64, 0u64);
        let lo = t.saturating_sub(21);
        for g in self.g_fail.iter().rev() { if g.s + 200 < lo { break; } if g.s >= lo && g.s <= tl && g.buy && bots.is_f(&g.payer) { gbf += 1; } }
        for g in self.g_tr.iter().rev() { if g.s + 200 < lo { break; } if g.s >= lo && g.s <= tl && g.buy && !g.ours && bots.is_f(&g.user) { gbb += 1; } }
        x.set("g_bfail_20s", gbf as f64);
        x.set("g_botbuys_20s", gbb as f64);
        let (Some(m), Some((rk, vr))) = (self.mints.get(&c.mint), c.r) else {
            for k in ["pf_n", "pf_bsol", "pf_ssol", "pf_buyers", "pf_sellers", "pf_bot_buys", "pf_bot_sells", "pf_bot_w", "pf_wh_sold", "pf_vmax", "pf_vmin", "pf_vlast",
                "pf_last_gap", "pf_bfail", "pf_bfail_w", "pf_bfail_last3", "pf_fail_all"] { x.set(k, f64::NAN); }
            return;
        };
        let p = m.rows.partition_point(|r| r.key() <= rk);
        let q: Vec<&Row> = m.rows[p..].iter().filter(|r| r.s < t).collect();
        let vr = vr as f64;
        x.set("pf_n", q.len() as f64);
        x.set("pf_bsol", q.iter().filter(|r| r.buy).map(|r| r.sol as f64).sum::<f64>() / 1e9);
        x.set("pf_ssol", q.iter().filter(|r| !r.buy).map(|r| r.sol as f64).sum::<f64>() / 1e9);
        let isf = |u: &Pk| bots.is_f(u) && !self.is_ours(u);
        x.set("pf_bot_buys", q.iter().filter(|r| r.buy && isf(&r.user)).count() as f64);
        x.set("pf_bot_sells", q.iter().filter(|r| !r.buy && isf(&r.user)).count() as f64);
        x.set("pf_wh_sold", q.iter().filter(|r| !r.buy && r.user == c.whale).count() as f64);
        x.set("pf_vmax", q.iter().map(|r| r.vsol).max().map_or(1.0, |v| v as f64 / vr));
        x.set("pf_vmin", q.iter().map(|r| r.vsol).min().map_or(1.0, |v| v as f64 / vr));
        x.set("pf_vlast", q.last().map_or(1.0, |r| r.vsol as f64 / vr));
        x.set("pf_buyers", q.iter().filter(|r| r.buy).map(|r| r.user).collect::<FxHashSet<Pk>>().len() as f64);
        x.set("pf_sellers", q.iter().filter(|r| !r.buy).map(|r| r.user).collect::<FxHashSet<Pk>>().len() as f64);
        x.set("pf_bot_w", q.iter().filter(|r| isf(&r.user)).map(|r| r.user).collect::<FxHashSet<Pk>>().len() as f64);
        x.set("pf_last_gap", q.last().map_or(tl as f64 - s as f64, |r| tl as f64 - r.s as f64));
        let post = |f: &Fail| (f.s > s || (f.s == s && f.i >= rk.1)) && f.s <= tl;
        let bf: Vec<&Fail> = m.fails.iter().filter(|f| post(f) && f.buy && bots.is_f(&f.payer)).collect();
        x.set("pf_bfail", bf.len() as f64);
        x.set("pf_bfail_w", bf.iter().map(|f| f.payer).collect::<FxHashSet<Pk>>().len() as f64);
        x.set("pf_bfail_last3", bf.iter().filter(|f| f.s + 3 >= t).count() as f64);
        x.set("pf_fail_all", m.fails.iter().filter(|f| post(f)).count() as f64);
    }
}

// =====================================================================================================================
// ARM-RECORD inputs (section 4, fp2_own.arm_fields) from the presend_live_arm record
// =====================================================================================================================
fn jf(v: &serde_json::Value) -> f64 { v.as_f64().unwrap_or(f64::NAN) }

pub fn arm_fields(rec: &serde_json::Value, t2: bool, x: &mut X) {
    let tr = if t2 { &rec["trig"] } else { &rec["dump"] };
    x.set("a_pct", jf(&tr["pct"]));
    x.set("a_sol", tr["sol"].as_f64().unwrap_or(0.0) / 1e9);
    x.set("a_age", jf(&tr["age_slots"]));
    x.set("a_vsol", tr["vsol"].as_f64().unwrap_or(0.0) / 1e9);
    x.set("a_nb", jf(&rec["nb"]));
    x.set("a_nb50", jf(&rec["ann"]["nb50"]));
    x.set("a_crpct", jf(&rec["ann"]["cr_pct"]));
    let q = if rec["quiet"].is_object() && !rec["quiet"].as_object().unwrap().is_empty() { &rec["quiet"] } else { &rec["r5"] };
    for (k, f) in [("q_coh_hold", "coh_hold"), ("q_fb_n", "fb_n"), ("q_since_last", "since_last"), ("q_wh_dumps", "wh_dumps"), ("q_wh_fol", "wh_fol")] { x.set(k, jf(&q[f])); }
    let v = &rec["v2"];
    let has_v = v.as_object().is_some_and(|o| !o.is_empty());
    x.set("v_n120", jf(&v["n_120s"]));
    x.set("v_dd120", jf(&v["maxdd_120s"]));
    x.set("v_ntr60", jf(&v["n_tr_60s"]));
    x.set("v_high", if has_v { if v["at_120s_high"].as_bool().unwrap_or(false) || v["at_120s_high"].as_f64().is_some_and(|z| z != 0.0) { 1.0 } else { 0.0 } } else { f64::NAN });
    let hs: Vec<f64> = rec["holders"].as_array().map(|a| a.iter().map(|h| h["pct"].as_f64().unwrap_or(0.0)).collect()).unwrap_or_default();
    x.set("h_n", hs.len() as f64);
    x.set("h_max", if hs.is_empty() { f64::NAN } else { hs.iter().copied().fold(f64::MIN, f64::max) });
    x.set("h_sum", if hs.is_empty() { f64::NAN } else { hs.iter().sum() });
    let t = tr["t"].as_f64().unwrap_or(0.0);
    x.set("t_hour", ((t / 1e9 + 5.0 * 3600.0) % 86400.0) / 3600.0);
    x.set("is_T2", if t2 { 1.0 } else { 0.0 });
}

// =====================================================================================================================
// OWN RESULTS and the SHADOW book (section 5, fp2_own.run_feats)
// =====================================================================================================================
#[derive(Clone, Debug, PartialEq)]
pub struct OwnPos { pub k: u64, pub pnl: f64, pub fol: f64, pub mint: Pk, pub whale: Option<Pk>, pub creator: Option<Pk> }

#[derive(Clone, Debug, Default)]
pub struct Book { pub own: Vec<OwnPos>, pub sh: Vec<(u64, f64)>, pub sh_arms: Vec<u64> }

fn is_flat(p: f64) -> bool { (-0.025..=0.0).contains(&p) }

impl Book {
    pub fn add_own(&mut self, p: OwnPos) {
        let at = self.own.partition_point(|z| z.k <= p.k);
        self.own.insert(at, p);
        if self.own.len() > OWN_CAP { self.own.remove(0); }
    }
    pub fn add_sh(&mut self, known: u64, val: f64) {
        let at = self.sh.partition_point(|z| z.0 <= known);
        self.sh.insert(at, (known, val));
        if self.sh.len() > SH_CAP { self.sh.remove(0); }
    }
    pub fn add_sh_arm(&mut self, t: u64) {
        let at = self.sh_arms.partition_point(|z| *z <= t);
        self.sh_arms.insert(at, t);
        if self.sh_arms.len() > SH_CAP { self.sh_arms.remove(0); }
    }

    pub fn feats(&self, t: u64, mint: &Pk, whale: Option<&Pk>, creator: Option<&Pk>, x: &mut X) {
        let j = self.own.partition_point(|z| z.k < t);
        let prev = &self.own[..j];
        for n in [5usize, 10, 20, 40] {
            let l = &prev[prev.len().saturating_sub(n)..];
            let ok = l.len() >= n.min(5);
            let nn = l.len() as f64;
            x.set(&format!("o_mean{n}"), if ok { l.iter().map(|z| z.pnl).sum::<f64>() / nn } else { f64::NAN });
            x.set(&format!("o_flat{n}"), if ok { l.iter().filter(|z| is_flat(z.pnl)).count() as f64 / nn } else { f64::NAN });
            x.set(&format!("o_win{n}"), if ok { l.iter().filter(|z| z.pnl >= 0.025).count() as f64 / nn } else { f64::NAN });
            x.set(&format!("o_fol{n}"), if ok { l.iter().map(|z| z.fol).sum::<f64>() / nn } else { f64::NAN });
        }
        for w in [15u64, 60] {
            let l: Vec<&OwnPos> = prev.iter().filter(|z| z.k as f64 >= t as f64 - w as f64 * 6e10).collect();
            let nn = l.len() as f64;
            x.set(&format!("o_n_{w}m"), nn);
            x.set(&format!("o_sum_{w}m"), l.iter().map(|z| z.pnl).sum::<f64>());
            x.set(&format!("o_flat_{w}m"), if l.is_empty() { f64::NAN } else { l.iter().filter(|z| is_flat(z.pnl)).count() as f64 / nn });
            x.set(&format!("o_win_{w}m"), if l.is_empty() { f64::NAN } else { l.iter().filter(|z| z.pnl >= 0.025).count() as f64 / nn });
        }
        x.set("o_lastwin_min", prev.iter().rev().find(|z| z.pnl >= 0.025).map_or(f64::NAN, |z| (t as f64 - z.k as f64) / 6e10));
        let same = |f: &dyn Fn(&OwnPos) -> bool| { let l: Vec<f64> = prev.iter().filter(|z| f(z)).map(|z| z.pnl).collect(); (l.len() as f64, if l.is_empty() { f64::NAN } else { l.iter().sum() }) };
        let (n, s) = same(&|z| z.mint == *mint);
        x.set("o_tok_n", n); x.set("o_tok_sum", s);
        let (n, s) = match whale { Some(w) => same(&|z| z.whale.as_ref() == Some(w)), None => (0.0, f64::NAN) };
        x.set("o_wh_n", n); x.set("o_wh_sum", s);
        let (n, s) = match creator { Some(c) => same(&|z| z.creator.as_ref() == Some(c)), None => (0.0, f64::NAN) };
        x.set("o_cr_n", n); x.set("o_cr_sum", s);
        // the shadow's row c
        let js = self.sh.partition_point(|z| z.0 < t);
        for n in [10usize, 30] {
            let l: Vec<f64> = self.sh[js.saturating_sub(n)..js].iter().map(|z| z.1).collect();
            x.set(&format!("s_mean{n}"), if l.len() >= 5 { mean(&l) } else { f64::NAN });
            x.set(&format!("s_pos{n}"), if l.len() >= 5 { l.iter().filter(|v| **v > 0.005).count() as f64 / l.len() as f64 } else { f64::NAN });
        }
        let l: Vec<f64> = self.sh[..js].iter().filter(|z| z.0 as f64 >= t as f64 - 15.0 * 6e10).map(|z| z.1).collect();
        x.set("s_n_15m", l.len() as f64);
        x.set("s_mean_15m", if l.is_empty() { f64::NAN } else { mean(&l) });
        let a = self.sh_arms.partition_point(|z| *z < t);
        let b = self.sh_arms.partition_point(|z| (*z as f64) < t as f64 - 5.0 * 6e10);
        x.set("s_arms_5m", (a - b) as f64);
    }
}

// =====================================================================================================================
// THE PRELOAD FILE (ops/strategies/presend/flatperfect/fp_preload.py): line 1 = a JSON header, then binary little-endian:
//   wallets  N x 32 bytes
//   rows     M x 17 bytes: wallet index u32, mint id u64 (pk64), slot u32, flags u8 (1 = buy, 2 = big >= 6%)
// header {"fpnb_preload": 1, "from_slot", "to_slot", "wallets": N, "rows": M, "own": [{k, pnl, fol, mint, whale, creator}],
//         "shadow": [[known_ns, net_cheap]], "shadow_arms": [t_ns], ...}
// =====================================================================================================================
#[derive(Default)]
pub struct Preload { pub span: PreSpan, pub wh: Vec<(Pk, WRow)>, pub own: Vec<OwnPos>, pub sh: Vec<(u64, f64)>, pub sh_arms: Vec<u64>, pub head: serde_json::Value }

pub fn preload_parse(b: &[u8]) -> Result<Preload, String> {
    let nl = b.iter().position(|c| *c == b'\n').ok_or("no header line")?;
    let h: serde_json::Value = serde_json::from_slice(&b[..nl]).map_err(|e| format!("header: {e}"))?;
    if h["fpnb_preload"].as_u64() != Some(1) { return Err("not an fpnb preload (v1)".into()); }
    let nw = h["wallets"].as_u64().ok_or("no wallets")? as usize;
    let nr = h["rows"].as_u64().ok_or("no rows")? as usize;
    let body = &b[nl + 1..];
    if body.len() != nw * 32 + nr * 17 { return Err(format!("size {} != {} wallets + {} rows", body.len(), nw, nr)); }
    let ws: Vec<Pk> = body[..nw * 32].chunks_exact(32).map(|c| c.try_into().unwrap()).collect();
    let mut wh = Vec::with_capacity(nr);
    for c in body[nw * 32..].chunks_exact(17) {
        let wi = u32::from_le_bytes(c[0..4].try_into().unwrap()) as usize;
        let w = *ws.get(wi).ok_or("wallet index out of range")?;
        wh.push((w, WRow { m: u64::from_le_bytes(c[4..12].try_into().unwrap()), s: u32::from_le_bytes(c[12..16].try_into().unwrap()), f: c[16] }));
    }
    let opk = |v: &serde_json::Value| v.as_str().and_then(pk);
    let own = h["own"].as_array().map(|a| a.iter().filter_map(|o| Some(OwnPos { k: o["k"].as_u64().or_else(|| o["k"].as_f64().map(|v| v as u64))?, pnl: o["pnl"].as_f64()?, fol: o["fol"].as_f64().unwrap_or(0.0),
        mint: opk(&o["mint"])?, whale: opk(&o["whale"]), creator: opk(&o["creator"]) })).collect()).unwrap_or_default();
    let sh = h["shadow"].as_array().map(|a| a.iter().filter_map(|z| Some((z[0].as_f64()? as u64, z[1].as_f64()?))).collect()).unwrap_or_default();
    let sh_arms = h["shadow_arms"].as_array().map(|a| a.iter().filter_map(|z| z.as_f64().map(|v| v as u64)).collect()).unwrap_or_default();
    let span = PreSpan { from: h["from_slot"].as_u64().ok_or("no from_slot")?, to: h["to_slot"].as_u64().ok_or("no to_slot")? };
    let mut head = h;
    for k in ["own", "shadow", "shadow_arms"] { if let Some(o) = head.as_object_mut() { o.remove(k); } }
    Ok(Preload { span, wh, own, sh, sh_arms, head })
}

// =====================================================================================================================
// dip36 SKIP-2 PER-SEND (LOG-ONLY; owner 11-05 PKT; spec /home/moiz/sniper-data/skip2/ENGINE_SPEC_PERSEND.txt, reference s2_table.py): a
// frozen logistic score (72 inputs, standardised, b + w.z; log-odds of P&L > 0). Inputs 1-34 from the arm record + the arm clock, 35-55
// from our own history / ledgers (S2Hist: the records emitted before the arm; the creator / whale / mint ledgers seeded from a file),
// 56-72 = FP-NOBOT's pf_* (the same store). would_skip = covered && score < thr[kind]. Also scored with the 4 failed-tx inputs missing.
// =====================================================================================================================
pub const S2_MODEL_JSON: &str = include_str!("fpnb_models/skip2_persend.json");
/// inputs 56-59 (other wallets' failed txs): the "nf" score sets them missing
pub const S2_FAIL_IX: [usize; 4] = [55, 56, 57, 58];
pub const S2_N: usize = 72;
pub const S2_ARM_N: usize = 55;

#[derive(Clone, Debug)]
pub struct S2Model { pub feats: Vec<String>, med: Vec<f64>, mu: Vec<f64>, sd: Vec<f64>, w: Vec<f64>, b: f64, pub thr_t2: f64, pub thr_rearm: f64 }

impl S2Model {
    pub fn frozen() -> Result<S2Model, String> { S2Model::parse(S2_MODEL_JSON) }
    pub fn parse(s: &str) -> Result<S2Model, String> {
        let v: serde_json::Value = serde_json::from_str(s).map_err(|e| e.to_string())?;
        let fl = |k: &str| -> Result<Vec<f64>, String> { v[k].as_array().ok_or(format!("no {k}"))?.iter().map(|x| x.as_f64().ok_or(format!("{k}: not a number"))).collect() };
        let feats: Vec<String> = v["features"].as_array().ok_or("no features")?.iter().map(|x| x.as_str().unwrap_or("").to_string()).collect();
        let m = S2Model { med: fl("median_fill")?, mu: fl("mu")?, sd: fl("sd")?, w: fl("w")?, b: v["b"].as_f64().ok_or("no b")?,
            thr_t2: v["thr"]["T2"].as_f64().ok_or("no thr T2")?, thr_rearm: v["thr"]["rearm"].as_f64().ok_or("no thr rearm")?, feats };
        if [m.feats.len(), m.med.len(), m.mu.len(), m.sd.len(), m.w.len()].iter().any(|n| *n != S2_N) { return Err("not 72 inputs".into()); }
        for (k, f) in ["pf_bfail", "pf_bfail_w", "pf_bfail_last3", "pf_fail_all"].iter().enumerate() { if m.feats[S2_FAIL_IX[k]] != *f { return Err("the failed-tx inputs moved".into()); } }
        Ok(m)
    }
    pub fn thr(&self, t2: bool) -> f64 { if t2 { self.thr_t2 } else { self.thr_rearm } }
    /// the score of the raw inputs (NaN -> median_fill)
    pub fn score(&self, x: &[f64]) -> f64 {
        let mut s = 0.0;
        for i in 0..S2_N {
            let v = if x[i].is_nan() { self.med[i] } else { x[i] };
            s += self.w[i] * ((v - self.mu[i]) / self.sd[i]);
        }
        self.b + s
    }
    /// the score with the 4 failed-tx inputs missing
    pub fn score_nf(&self, x: &[f64]) -> f64 {
        let mut y = x.to_vec();
        for i in S2_FAIL_IX { y[i] = f64::NAN; }
        self.score(&y)
    }
    /// the full 72 from the 55 arm inputs and FP-NOBOT's inputs (the pf_* of its send)
    pub fn full(&self, arm: &[f64], fp: &X) -> Vec<f64> {
        let mut x = arm.to_vec();
        for f in &self.feats[S2_ARM_N..] { x.push(fp.get(f)); }
        x
    }
}

fn nz(v: &serde_json::Value) -> f64 { v.as_f64().unwrap_or(f64::NAN) }
fn obj_nonempty(v: &serde_json::Value) -> bool { v.as_object().is_some_and(|o| !o.is_empty()) }
fn truthy(v: &serde_json::Value) -> bool { v.as_bool().unwrap_or(false) || v.as_f64().is_some_and(|x| x != 0.0) }

/// inputs 1-34 from the arm record (presend_live_arm) and the arm clock (ns)
pub fn s2_arm_fields(d: &serde_json::Value, clk: u64) -> Vec<f64> {
    let t2 = d["kind"].as_str().is_none_or(|k| k == "T2");
    let tr = if t2 { &d["trig"] } else { &d["dump"] };
    let ann = &d["ann"];
    let q = if obj_nonempty(&d["quiet"]) { &d["quiet"] } else { &serde_json::Value::Null };
    let v = &d["v2"];
    let hv = obj_nonempty(v);
    let whale = if t2 { tr["wallet"].as_str() } else { tr["seller"].as_str() };
    let creator = ann["creator"].as_str().filter(|s| !s.is_empty());
    let hr = ((clk as f64 / 1e9 + 5.0 * 3600.0) % 86400.0) / 3600.0;
    let ang = hr / 24.0 * 2.0 * std::f64::consts::PI;
    let qq = |i: usize| match q["q"].as_array().filter(|a| !a.is_empty()) { Some(a) => if truthy(&a[i]) { 1.0 } else { 0.0 }, None => f64::NAN };
    let hs: Vec<f64> = d["holders"].as_array().map(|a| a.iter().map(|h| h["pct"].as_f64().unwrap_or(0.0)).collect()).unwrap_or_default();
    let sol = tr["sol"].as_f64().filter(|s| *s != 0.0);
    let arm_slot = d["arm_slot"].as_f64().filter(|s| *s != 0.0).unwrap_or(nz(&tr["slot"]));
    vec![
        if t2 { 1.0 } else { 0.0 }, ang.sin(), ang.cos(), nz(&d["spend"]) / 1e9,
        nz(&tr["pct"]), sol.map_or(f64::NAN, |s| (s / 1e9).ln_1p()), nz(&tr["age_slots"]), nz(&tr["vsol"]) / 1e9, nz(&tr["drop_pct"]),
        match creator { None => f64::NAN, Some(c) => if whale == Some(c) { 1.0 } else { 0.0 } },
        nz(&d["nb"]), nz(&ann["nb50"]), nz(&ann["cr_pct"]),
        nz(&q["coh_hold"]), nz(&q["fb_n"]), nz(&q["since_last"]), nz(&q["wh_dumps"]), nz(&q["wh_fol"]), qq(0), qq(1), qq(2), qq(3),
        nz(&v["n_120s"]), nz(&v["maxdd_120s"]), nz(&v["n_tr_60s"]), nz(&v["ring_s"]), if hv { if truthy(&v["at_120s_high"]) { 1.0 } else { 0.0 } } else { f64::NAN },
        nz(&d["arm_ms_after_dump"]), nz(&d["deferred_ms"]), nz(&d["gap"]),
        if t2 { f64::NAN } else { hs.len() as f64 }, if t2 { f64::NAN } else { hs.iter().copied().fold(0.0, f64::max) }, if t2 { f64::NAN } else { hs.iter().sum() },
        nz(&d["en_slot"]) - arm_slot,
    ]
}

/// our own history and the ledgers (inputs 35-55), from the records in emission order (s2_table.py); the ledgers can be seeded
#[derive(Clone, Debug, Default)]
pub struct S2Hist {
    real: Vec<(u64, f64)>,
    arms_t: VecDeque<u64>,
    skips_t: VecDeque<u64>,
    dis: VecDeque<f64>,
    cre: FxHashMap<String, (f64, f64, f64)>,
    wh: FxHashMap<String, (f64, f64, f64, f64, f64)>,
    mint: FxHashMap<String, (f64, f64, f64)>,
    armmeta: FxHashMap<(String, u64), (String, Option<String>)>,
    pub seeded: usize,
}

const S2_KEEP_NS: u64 = 3_700_000_000_000;

impl S2Hist {
    /// the ledger seed (s2_seed.py): {"cre": {c: [n, sum, arms]}, "wh": {w: [n, sum, arms, disarms, fills]}, "mint": {m: [n, sum, arms]}}
    pub fn seed(&mut self, b: &[u8]) -> Result<usize, String> {
        let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| e.to_string())?;
        let a = |x: &serde_json::Value, i: usize| x[i].as_f64().unwrap_or(0.0);
        for (k, x) in v["cre"].as_object().ok_or("no cre")? { self.cre.insert(k.clone(), (a(x, 0), a(x, 1), a(x, 2))); }
        for (k, x) in v["wh"].as_object().ok_or("no wh")? { self.wh.insert(k.clone(), (a(x, 0), a(x, 1), a(x, 2), a(x, 3), a(x, 4))); }
        for (k, x) in v["mint"].as_object().ok_or("no mint")? { self.mint.insert(k.clone(), (a(x, 0), a(x, 1), a(x, 2))); }
        self.seeded = self.cre.len() + self.wh.len() + self.mint.len();
        Ok(self.seeded)
    }

    /// inputs 35-55 at the arm clock `now`
    pub fn feats(&self, now: u64, mint: &str, whale: &str, creator: Option<&str>) -> Vec<f64> {
        let lo = |span: u64| now.saturating_sub(span);
        let r60: Vec<f64> = self.real.iter().filter(|z| z.0 >= lo(3_600_000_000_000)).map(|z| z.1).collect();
        let last20 = &self.real[self.real.len().saturating_sub(20)..];
        let last10 = &self.real[self.real.len().saturating_sub(10)..];
        let cnt = |q: &VecDeque<u64>, span: u64| q.iter().filter(|t| **t >= lo(span)).count() as f64;
        let share = |f: &dyn Fn(f64) -> bool| if last20.is_empty() { f64::NAN } else { last20.iter().filter(|z| f(z.1)).count() as f64 / last20.len() as f64 };
        let c = creator.map(|c| self.cre.get(c).copied().unwrap_or_default());
        let w = self.wh.get(whale).copied().unwrap_or_default();
        let m = self.mint.get(mint).copied().unwrap_or_default();
        let d30: Vec<f64> = self.dis.iter().rev().take(30).copied().collect();
        vec![
            r60.len() as f64, r60.iter().sum(), if self.real.is_empty() { f64::NAN } else { last10.iter().map(|z| z.1).sum() },
            share(&|p| (-0.025..=0.0).contains(&p)), share(&|p| p >= 0.025),
            self.real.last().map_or(f64::NAN, |z| (now as f64 - z.0 as f64) / 60e9),
            cnt(&self.arms_t, 600_000_000_000), cnt(&self.arms_t, 3_600_000_000_000), cnt(&self.skips_t, 600_000_000_000), cnt(&self.skips_t, 3_600_000_000_000),
            if d30.is_empty() { f64::NAN } else { d30.iter().sum::<f64>() / d30.len() as f64 },
            c.map_or(f64::NAN, |c| c.0), c.map_or(f64::NAN, |c| c.1), c.map_or(f64::NAN, |c| c.2),
            w.0, w.1, w.2, if w.3 > 0.0 { w.4 / w.3 } else { f64::NAN },
            m.2, m.0, m.1,
        ]
    }
    fn trim(&mut self, now: u64) {
        while self.arms_t.front().is_some_and(|t| *t + S2_KEEP_NS < now) { self.arms_t.pop_front(); }
        while self.skips_t.front().is_some_and(|t| *t + S2_KEEP_NS < now) { self.skips_t.pop_front(); }
        while self.dis.len() > 30 { self.dis.pop_front(); }
        if self.real.len() > 4096 { self.real.drain(..2048); }
        if self.armmeta.len() > 100_000 { self.armmeta.clear(); }
    }
    /// an arm (after its inputs were computed)
    pub fn on_arm(&mut self, now: u64, mint: &str, w: u64, whale: &str, creator: Option<&str>) {
        self.arms_t.push_back(now);
        self.wh.entry(whale.to_string()).or_default().2 += 1.0;
        self.mint.entry(mint.to_string()).or_default().2 += 1.0;
        if let Some(c) = creator { self.cre.entry(c.to_string()).or_default().2 += 1.0; }
        self.armmeta.insert((mint.to_string(), w), (whale.to_string(), creator.map(|c| c.to_string())));
        self.trim(now);
    }
    pub fn on_skip(&mut self, now: u64) { self.skips_t.push_back(now); self.trim(now); }
    pub fn on_disarm(&mut self, mint: &str, w: u64, filled: bool) {
        self.dis.push_back(if filled { 1.0 } else { 0.0 });
        if let Some((wh, _)) = self.armmeta.get(&(mint.to_string(), w)) {
            let e = self.wh.entry(wh.clone()).or_default();
            e.3 += 1.0;
            if filled { e.4 += 1.0; }
        }
        while self.dis.len() > 30 { self.dis.pop_front(); }
    }
    pub fn on_real(&mut self, now: u64, mint: &str, w: Option<u64>, pnl: f64) {
        self.real.push((now, pnl));
        let m = self.mint.entry(mint.to_string()).or_default();
        m.0 += 1.0; m.1 += pnl;
        if let Some((wh, cr)) = w.and_then(|w| self.armmeta.get(&(mint.to_string(), w))).cloned() {
            let e = self.wh.entry(wh).or_default();
            e.0 += 1.0; e.1 += pnl;
            if let Some(c) = cr { let e = self.cre.entry(c).or_default(); e.0 += 1.0; e.1 += pnl; }
        }
        self.trim(now);
    }
}

#[cfg(test)]
#[path = "fpnb_tests.rs"]
mod tests;
