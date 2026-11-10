//! APEX-3 ENTRY SCORE (11-04): a port of the APEX-3 backtest's create-time entry model (sniper-apex3 run3_lib.py: feature
//! row X + gbdt_np score) so the probe scores every watched create exactly as the backtest scored its picks.
//!
//! The model file is written by ops/apex_probe/entry_export.py from the APEX-3 code itself (trees, bin edges, threshold,
//! creator history); doubles are repr strings, parsed here to the identical f64.
//!
//! Features (run3_lib order):
//!  0 dev_sol      SOL of the create tx's FIRST pump trade if it is a buy (TradeEvent sol = curve SOL, pump fee excluded)
//!  1 bund_sol     curve SOL of the creator-bundle buys right after the create in the create slot
//!  2 bund_users   distinct buyers of those bundle buys
//!  3 u            create's tx index / block size (the slot's max pump-tx index + 1)                 [NOT VISIBLE live]
//!  4 hour_pkt     ((block time // 3600) + 5) % 24
//!  5..10          creator history: launches resolved >= 15 s before this create (count, mean label, mean fol2, share of
//!                 positive labels, seconds since the latest one, max fol2); label / fol2 come from the APEX-3 replay
//!                 (s3_sim + ev3.s2_label), so the probe has them only for launches in the exported file
//!
//! What the probe sees before signing, and the approximations (documented in ops/apex_probe/README.md):
//!  - dev_sol: exact from the create tx's buy legs (snipe::bundle_legs + simulate_legs, the same fee math as the
//!    first-or-revert state); a router create's CPI buy: launch.dev_buy_lamports net of fee.
//!  - bund_sol / bund_users: the bundle legs the first-or-revert window saw (create slot, before signing); the tape's rule is
//!    "consecutive tx indices", the window's is "same slot, before the create's feed moved on / --bundle-wait-us"; buyer =
//!    the bundle tx's fee payer. No window (bundle_wait auto with no hint, or --no-first-or-revert) = 0 bundle.
//!  - u: the block index and block size are unknown at create time from shreds. Approximation: the entries feed's PoH
//!    position (hashes / (64 x hashes per tick) = position / the previous slot's total, D1 in ops/dip/speed/fixes/FIXES.md)
//!    when the create came with PoH, else `u_default` (the training median). Recorded as `u_src`.
//!  - history: frozen at the export (the backtest also uses launches of the same day >= 15 s old: re-export to refresh).
use arbx::tx::Pk;
use std::collections::HashMap;

pub const NF: usize = 11;
pub const FEATURES: [&str; NF] = ["dev_sol", "bund_sol", "bund_users", "u", "hour_pkt", "n_hist", "mean_label", "mean_fol2", "frac_label_pos", "since_last_s", "max_fol2"];

/// --entry-filter: off (no score) | log (score recorded, never gates: the default) | on (skip a create scoring under thr)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EntryMode { Off, Log, On }

impl EntryMode {
    pub fn parse(s: &str) -> Result<EntryMode, String> {
        match s { "off" => Ok(EntryMode::Off), "log" => Ok(EntryMode::Log), "on" => Ok(EntryMode::On), _ => Err(format!("--entry-filter {s}: on|off|log")) }
    }
}

#[derive(Clone, Debug)]
enum Node { Leaf(f64), Split { f: usize, b: u32, l: usize, r: usize } }

/// one creator's resolved launch: block time, label, fol2, label is a float32 (run3_lib: the replay value is float32; the
/// no-fill label -CREV is a python float). Block-time order (the export's L order).
#[derive(Clone, Copy, Debug)]
struct HRow { bt: i64, label: f64, fol: f64, f32: bool }
type Hist = Vec<HRow>;

pub struct EntryModel {
    pub name: String,
    pub f0: f64,
    pub lr: f64,
    pub edges: Vec<Vec<f64>>,
    trees: Vec<Vec<Node>>,
    pub thr: f64,
    pub resolve_s: i64,
    pub hour_offset_h: i64,
    pub data_end_bt: i64,
    pub u_default: f64,
    hist: HashMap<Pk, Hist>,
    pub sha256: String,
}

/// what the probe observed about one create (see the module doc)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Obs { pub dev_sol: f64, pub bund_sol: f64, pub bund_users: f64, pub u: f64, pub bt: i64 }

/// a scored create: the features, the score, the threshold and the verdict
#[derive(Clone, Debug)]
pub struct Scored { pub x: [f64; NF], pub score: f64, pub thr: f64, pub pass: bool }

fn num(v: &serde_json::Value, what: &str) -> Result<f64, String> {
    match v {
        serde_json::Value::String(s) => s.parse::<f64>().map_err(|e| format!("{what}: {s}: {e}")),
        // plain JSON numbers are accepted too (not bit-exact through serde_json: the exporter writes strings)
        serde_json::Value::Number(n) => n.as_f64().ok_or(format!("{what}: not a number")),
        _ => Err(format!("{what}: not a number")),
    }
}

/// numpy's float64 add.reduce (pairwise_sum, 8-way unrolled blocks of <= 128): np.mean / np.sum bit for bit
pub fn np_sum(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut r = 0.0;
        for &x in a { r += x; }
        r
    } else if n <= 128 {
        let mut r = [0.0f64; 8];
        r.copy_from_slice(&a[..8]);
        let mut i = 8;
        while i < n - (n % 8) {
            for j in 0..8 { r[j] += a[i + j]; }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n { res += a[i]; i += 1; }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        np_sum(&a[..n2]) + np_sum(&a[n2..])
    }
}

pub fn np_mean(a: &[f64]) -> f64 { if a.is_empty() { f64::NAN } else { np_sum(a) / a.len() as f64 } }

/// the same for a float32 array (numpy keeps float32: pairwise sum in f32, then f32 division)
pub fn np_sum32(a: &[f32]) -> f32 {
    let n = a.len();
    if n < 8 {
        let mut r = 0.0f32;
        for &x in a { r += x; }
        r
    } else if n <= 128 {
        let mut r = [0.0f32; 8];
        r.copy_from_slice(&a[..8]);
        let mut i = 8;
        while i < n - (n % 8) {
            for j in 0..8 { r[j] += a[i + j]; }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n { res += a[i]; i += 1; }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        np_sum32(&a[..n2]) + np_sum32(&a[n2..])
    }
}

pub fn np_mean32(a: &[f32]) -> f32 { if a.is_empty() { f32::NAN } else { np_sum32(a) / a.len() as f32 } }

impl EntryModel {
    pub fn load(path: &str) -> Result<EntryModel, String> {
        let text = std::fs::read(path).map_err(|e| format!("{path}: {e}"))?;
        let mut m = EntryModel::parse(std::str::from_utf8(&text).map_err(|e| format!("{path}: {e}"))?)?;
        use sha2::Digest as _;
        m.sha256 = sha2::Sha256::digest(&text).iter().map(|b| format!("{b:02x}")).collect();
        Ok(m)
    }

    pub fn parse(text: &str) -> Result<EntryModel, String> {
        let v: serde_json::Value = serde_json::from_str(text).map_err(|e| format!("entry model: not valid JSON: {e}"))?;
        let fl = v["features"].as_array().map(|a| a.iter().filter_map(|x| x.as_str()).collect::<Vec<_>>()).unwrap_or_default();
        if fl != FEATURES { return Err(format!("entry model: features {fl:?} != {FEATURES:?}")); }
        let edges: Vec<Vec<f64>> = v["edges"].as_array().ok_or("entry model: no edges")?.iter().enumerate()
            .map(|(j, e)| e.as_array().ok_or(format!("edges[{j}]"))?.iter().map(|x| num(x, "edge")).collect::<Result<Vec<_>, _>>())
            .collect::<Result<_, _>>()?;
        if edges.len() != NF { return Err(format!("entry model: {} edge lists", edges.len())); }
        let mut trees = Vec::new();
        for (ti, t) in v["trees"].as_array().ok_or("entry model: no trees")?.iter().enumerate() {
            let nodes = t.as_array().ok_or(format!("tree {ti}"))?;
            let mut out = Vec::with_capacity(nodes.len());
            for (ni, n) in nodes.iter().enumerate() {
                let a = n.as_array().ok_or(format!("tree {ti} node {ni}"))?;
                let f = a.first().and_then(|x| x.as_i64()).ok_or(format!("tree {ti} node {ni}: f"))?;
                if f < 0 {
                    out.push(Node::Leaf(num(a.get(1).ok_or("leaf")?, "leaf")?));
                } else {
                    let g = |k: usize| a.get(k).and_then(|x| x.as_u64()).ok_or(format!("tree {ti} node {ni}: [{k}]"));
                    let (b, l, r) = (g(1)? as u32, g(2)? as usize, g(3)? as usize);
                    if f as usize >= NF || l >= nodes.len() || r >= nodes.len() || l <= ni || r <= ni { return Err(format!("tree {ti} node {ni}: bad split")); }
                    out.push(Node::Split { f: f as usize, b, l, r });
                }
            }
            if out.is_empty() { return Err(format!("tree {ti}: empty")); }
            trees.push(out);
        }
        if trees.is_empty() { return Err("entry model: 0 trees".into()); }
        let mut hist: HashMap<Pk, Hist> = HashMap::new();
        if let Some(h) = v["hist"].as_object() {
            for (c, rows) in h {
                let Some(pk) = super::logic::parse_pk(c) else { return Err(format!("hist: bad creator {c}")) };
                let mut out: Hist = Vec::new();
                for r in rows.as_array().ok_or("hist rows")? {
                    out.push(HRow { bt: r[0].as_i64().ok_or("hist bt")?, label: num(&r[1], "hist label")?, fol: num(&r[2], "hist fol2")?,
                        f32: r.get(3).and_then(|x| x.as_i64()) == Some(1) });
                }
                hist.insert(pk, out);
            }
        }
        let u_default = match &v["u_default"] { serde_json::Value::Null => 0.5, x => num(x, "u_default")? };
        Ok(EntryModel {
            name: v["name"].as_str().unwrap_or("entry").to_string(), f0: num(&v["f0"], "f0")?, lr: num(&v["lr"], "lr")?, edges, trees,
            thr: num(&v["thr"], "thr")?, resolve_s: v["resolve_s"].as_i64().unwrap_or(15), hour_offset_h: v["hour_offset_h"].as_i64().unwrap_or(5),
            data_end_bt: v["data_end_bt"].as_i64().unwrap_or(0), u_default, hist, sha256: String::new(),
        })
    }

    pub fn n_trees(&self) -> usize { self.trees.len() }
    pub fn n_creators(&self) -> usize { self.hist.len() }

    /// run3_lib's feature row for a create by `creator` (the CreateEvent creator) with these observations
    pub fn features(&self, creator: &Pk, o: &Obs) -> [f64; NF] {
        let h: &[HRow] = match self.hist.get(creator) {
            Some(v) => { let k = v.partition_point(|r| r.bt <= o.bt - self.resolve_s); &v[..k] }
            None => &[],
        };
        let lab: Vec<f64> = h.iter().map(|r| r.label).collect();
        let fol: Vec<f64> = h.iter().map(|r| r.fol).collect();
        let pos: Vec<f64> = lab.iter().map(|&x| if x > 0.0 { 1.0 } else { 0.0 }).collect();
        // np.mean(lab): float32 when every label is a numpy float32, float64 once a python float is in the list
        let mean_lab = if h.iter().all(|r| r.f32) { np_mean32(&lab.iter().map(|&x| x as f32).collect::<Vec<_>>()) as f64 } else { np_mean(&lab) };
        let e = h.is_empty();
        [o.dev_sol, o.bund_sol, o.bund_users, o.u, (o.bt.div_euclid(3600) + self.hour_offset_h).rem_euclid(24) as f64, h.len() as f64,
         if e { f64::NAN } else { mean_lab }, if e { f64::NAN } else { np_mean(&fol) }, if e { f64::NAN } else { np_mean(&pos) },
         if e { f64::NAN } else { (o.bt - h[h.len() - 1].bt) as f64 }, if e { f64::NAN } else { fol.iter().copied().fold(f64::NEG_INFINITY, f64::max) }]
    }

    /// gbdt_np: bin = #edges <= x (searchsorted right) + 1, NaN = 0; score = F0 + sum lr * leaf, trees in order
    pub fn score_x(&self, x: &[f64; NF]) -> f64 {
        let mut bins = [0u32; NF];
        for j in 0..NF { bins[j] = if x[j].is_nan() { 0 } else { self.edges[j].partition_point(|&e| e <= x[j]) as u32 + 1 }; }
        let mut f = self.f0;
        for t in &self.trees {
            let mut i = 0usize;
            let w = loop {
                match &t[i] { Node::Leaf(w) => break *w, Node::Split { f, b, l, r } => i = if bins[*f] <= *b { *l } else { *r } }
            };
            f += self.lr * w;
        }
        f
    }

    pub fn score(&self, creator: &Pk, o: &Obs) -> Scored {
        let x = self.features(creator, o);
        let s = self.score_x(&x);
        Scored { x, score: s, thr: self.thr, pass: s >= self.thr }
    }
}

// ------------------------------------------------------------------------------------------------------------------
// create-time legs -> the tape's TradeEvent SOL (exact pump math, verified on the 11-03 tape)
// ------------------------------------------------------------------------------------------------------------------

fn cdiv(a: u128, b: u128) -> u128 { a.div_ceil(b) }

/// pump.fun's buy on virtual reserves (v SOL, t tokens) -> (TradeEvent sol, tokens), None = the leg fails (its limit).
/// Exact-in (buy_exact_sol_in / buy_exact_quote_in_*: `a` = spend incl. fees, `b` = min tokens): sol = the largest n with
/// n + ceil(n x 95/1e4) + ceil(n x 30/1e4) <= a (14/14 dev legs on the 11-03 tape; the floor(a x 1e4/10125) shortcut is
/// 1 lamport high on 5/14), tokens = floor(t (n-1) / (v + n - 1)) (21,800/21,801 tape trades). Cap family (buy / buy_v2 /
/// buy_v3: `a` = tokens, `b` = max SOL): sol = floor(a v / (t - a)) + 1 (49,991/50,000 tape trades). Standard 95 + 30 bps.
pub fn pump_buy(v: u64, t: u64, leg: (bool, u64, u64)) -> Option<(u64, u64)> {
    let (exact, a, b) = leg;
    let (v, t) = (v as u128, t as u128);
    if exact {
        let a = a as u128;
        let mut n = a * 10_000 / 10_125;
        while n > 0 && n + cdiv(n * 95, 10_000) + cdiv(n * 30, 10_000) > a { n -= 1; }
        if n < 2 { return None; }
        let tok = t * (n - 1) / (v + n - 1);
        if b > 0 && tok < b as u128 { return None; }
        Some((n as u64, tok as u64))
    } else {
        let tok = a as u128;
        if tok == 0 || tok >= t { return None; }
        let sol = tok * v / (t - tok) + 1;
        if b > 0 && sol + cdiv(sol * 95, 10_000) + cdiv(sol * 30, 10_000) > b as u128 { return None; }
        Some((sol as u64, tok as u64))
    }
}

/// the create-time observations on the fresh curve: TradeEvent SOL of the create tx's FIRST buy leg (the tape's dev_sol)
/// and the total of the bundle legs (bund_sol). A failing leg is skipped (its tx would revert: no TradeEvent).
pub fn leg_sols(create_legs: &[(bool, u64, u64)], bundle_legs: &[(bool, u64, u64)]) -> (u64, u64) {
    let (mut v, mut t) = (arbx::snipe::CURVE_VQ0, arbx::snipe::CURVE_VT0);
    let mut dev = 0u64;
    for (i, l) in create_legs.iter().enumerate() {
        let Some((s, k)) = pump_buy(v, t, *l) else { continue };
        if i == 0 { dev = s; }
        v += s; t -= k;
    }
    let mut bund = 0u64;
    for l in bundle_legs {
        let Some((s, k)) = pump_buy(v, t, *l) else { continue };
        bund += s; v += s; t -= k;
    }
    (dev, bund)
}

/// launch-tool wrappers whose bundle / dev buys reach pump by CPI (layouts read off the 11-03 tape; validate with
/// --entry-validate --entry-txs). rapidlaunch: data [0] = 0, [1..9] = SOL spent incl. pump fees (no wrapper fee).
pub static RAPID: std::sync::LazyLock<Pk> = std::sync::LazyLock::new(|| arbx::tx::pk("rapidV5DAKtecYzetwCNoxXWHpezjeg4hGt9BGiVcGW"));
/// GMGN router: pump's `buy` discriminator, [8..16] = SOL spent (exact-in), [16..24] = min tokens; user = account 6
pub static GMGN: std::sync::LazyLock<Pk> = std::sync::LazyLock::new(|| arbx::tx::pk("GMgnVFR8Jb39LoXsEVzb3DvBy3ywCmdmJquHUy1Lrkqb"));
/// Axiom-style terminal ("term9Y"): ix e517cb977ae3ad2a (60 bytes), [14..22] = SOL in; 1% platform fee before pump
pub static TERM: std::sync::LazyLock<Pk> = std::sync::LazyLock::new(|| arbx::tx::pk("term9YPb9mzAsABaqN71A4xdbxHmpBNZavpBiQKZzN3"));
const TERM_BUY: [u8; 8] = [0xe5, 0x17, 0xcb, 0x97, 0x7a, 0xe3, 0xad, 0x2a];

/// one tx's buy legs on `mint` for the entry score, with each leg's buyer (the first signer among the buy's accounts: the
/// pump `user`; multi-wallet bundle txs have one per leg). More lenient than snipe::bundle_legs (first-or-revert): other
/// pump ixs (extend_account ...) are ignored, and rapidlaunch's wrapper is read. Unseen = touches the mint with no
/// readable buy (another router's CPI: its SOL is not in the ix data we know).
#[derive(Clone, Debug, PartialEq)]
pub enum ELegs { Buys(Vec<((bool, u64, u64), Pk)>), NotBuy, Unseen }

fn key_at(tx: &arbx::tx::Tx, i: usize) -> Option<Pk> {
    if let Some(k) = tx.keys.get(i) { return Some(*k); }
    let (w, r) = tx.loaded.as_ref()?;
    let j = i - tx.keys.len();
    w.get(j).or_else(|| r.get(j.checked_sub(w.len())?)).copied()
}

pub fn entry_legs(tx: &arbx::tx::Tx, mint: &Pk) -> Option<ELegs> {
    use arbx::snipe::{BUY_DISC, BUY_EXACT_QUOTE_IN_V3_DISC, BUY_EXACT_SOL_IN_DISC, BUY_V3_DISC, DEV_BUY_SOL_AT_16, DEV_BUY_SOL_AT_8, PUMP};
    use arbx::snipe_build::{SELL_DISC, SELL_EXACT_TOKENS_IN_V3_DISC, SELL_V3_DISC};
    let has_mint = tx.keys.contains(mint) || tx.loaded.as_ref().is_some_and(|(w, r)| w.contains(mint) || r.contains(mint));
    if !has_mint { return None; }
    let rd = |d: &[u8], off: usize| d.get(off..off + 8).and_then(|s| <[u8; 8]>::try_from(s).ok()).map(u64::from_le_bytes).unwrap_or(0);
    // the buyer: the layout's `user` when it signs (buy / buy_exact_sol_in 6, *_v3 8, *_v2 13), else the ix's first signer
    let signer = |ix: &arbx::tx::Ix, upos: Option<usize>| upos.and_then(|p| ix.accounts.get(p)).filter(|&&i| (i as usize) < tx.num_signers as usize)
        .or_else(|| ix.accounts.iter().find(|&&i| (i as usize) < tx.num_signers as usize)).and_then(|&i| tx.keys.get(i as usize)).copied()
        .or_else(|| tx.keys.first().copied()).unwrap_or([0u8; 32]);
    let mut v = Vec::new();
    let mut sell = false;
    for ix in &tx.ixs {
        let Some(prog) = key_at(tx, ix.program as usize) else { continue };
        if prog == *PUMP && ix.data.len() >= 8 {
            let d: [u8; 8] = ix.data[0..8].try_into().unwrap();
            let at8 = DEV_BUY_SOL_AT_8.contains(&d);
            if at8 || DEV_BUY_SOL_AT_16.contains(&d) {
                let (pos, upos) = if d == BUY_DISC || d == BUY_EXACT_SOL_IN_DISC { (2, 6) } else if d == BUY_V3_DISC || d == BUY_EXACT_QUOTE_IN_V3_DISC { (1, 8) } else { (1, 13) };
                if ix.accounts.get(pos).and_then(|&i| key_at(tx, i as usize)).map_or(true, |m| m == *mint) {
                    v.push(((at8, rd(&ix.data, 8), rd(&ix.data, 16)), signer(ix, Some(upos))));
                }
            } else if d == SELL_DISC || d == SELL_V3_DISC || d == SELL_EXACT_TOKENS_IN_V3_DISC {
                sell = true;
            }
        } else if prog == *RAPID && ix.data.len() >= 9 && ix.data[0] == 0 {
            v.push(((true, rd(&ix.data, 1), 0), signer(ix, None)));
        } else if prog == *GMGN && ix.data.len() >= 24 && ix.data[0..8] == BUY_DISC {
            v.push(((true, rd(&ix.data, 8), 0), signer(ix, Some(6))));
        } else if prog == *TERM && ix.data.len() == 60 && ix.data[0..8] == TERM_BUY {
            let a = rd(&ix.data, 14);
            v.push(((true, a - a / 100, 0), signer(ix, None)));
        }
    }
    Some(if sell { ELegs::NotBuy } else if v.is_empty() { ELegs::Unseen } else { ELegs::Buys(v) })
}

/// u from the entries feed's PoH position (see the module doc); None without PoH or before a tick fixed the rate
pub fn u_from_poh(p: Option<&arbx::feeds::entries::Poh>) -> Option<f64> {
    let p = p?;
    (p.hpt > 0).then(|| (p.hashes as f64 / (64.0 * p.hpt as f64)).clamp(0.0, 1.0))
}

/// hour + creator-history features need the block time: the probe uses the wall clock (block time = seconds, the create's
/// block lands within the second it is seen)
pub fn now_bt() -> i64 { std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0) }
