//! IMIT1 dip selector (ops/overnight/sel/SELECTION.md, frozen 2026-10-23): a GBDT that predicts which dumps (>= 1 SOL curve
//! sells) the three profitable dip bots (HkQ7hMjy, DYXDDrZC, haqqiUUX) buy, its 42 features at a dump, the watch envelope,
//! the dump-event rules and the per-token book a live engine keeps.
//! Ported line by line from ops/overnight/sel/selbuild.py `work` (= dip/dipbuy5.py + labels + token facts, with the
//! incremental cohort features of sel/selexit2.py) and sel/sel_lib.py (`fv`, tgt_*).
//! Parity with the Python: `cargo test --release --lib dip_imit` (testdata/imit1_parity.json, ops/dip/imit1/export_parity.py).
use crate::dip::{Gbdt, MIN_SELL, SLOT_MS};
use std::collections::{HashMap, HashSet};

/// one curve trade (one pump TradeEvent) of a token, in chain order (slot, tx index, event index). Synthetic gap trades
/// (rp.repair_gaps) have user "?" and `syn`.
#[derive(Clone, Debug, PartialEq)]
pub struct T { pub s: u64, pub i: u32, pub j: i32, pub sig: String, pub user: String, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64,
               pub fbps: u32, pub cbps: u32, pub syn: bool }

/// the launch (create tx) facts the features need (collector launches.jsonl)
#[derive(Clone, Debug, Default)]
pub struct LaunchInfo { pub slot: u64, pub idx: Option<u32>, pub creator: Option<String>, pub signer: Option<String>, pub sig: String, pub mayhem: bool }

/// rp.structure: the end of the dev's glued bundle in the trade list (index after it), the glued buys, the insiders
#[derive(Clone, Debug, Default)]
pub struct Structure { pub g_end: usize, pub glued: usize, pub insiders: HashSet<String> }

pub const FEATURES: [&str; 42] = ["age", "sell", "drop_pct", "vsol", "pb", "dd", "nb", "ns", "b20", "s20", "u20", "dev", "glued", "first_big", "ins",
    "s_frac", "s_pnl", "s_nb", "s_entry", "n_big", "since_big", "ret5", "ret20", "peak_mult", "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold",
    "net_flow", "slotpos", "prev_sell_ms", "n_tr", "vmax", "since_buy", "tgt_n", "tgt_since", "coh_n", "coh_20", "coh_seller", "coh_sol", "coh_held"];

/// the three wallets whose dip buys the model imitates (their earlier dip buys on a token are features)
pub const TARGETS: [&str; 3] = ["HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"];

/// Python's round(x, n) (correctly rounded decimal, ties to even on the exact binary value), via Rust's formatter
fn rnd(x: f64, n: usize) -> f64 { format!("{:.*}", n, x).parse().unwrap_or(x) }
fn px(t: &T) -> f64 { t.vsol as f64 / t.vtok as f64 }

/// a trade's arrival on the replay's block-position clock: slot x 212 ms + index / block size x 212 ms (block size 400 when
/// unknown; never below index + 1)
pub fn arr(t: &T, ss: &dyn Fn(u64) -> Option<u64>) -> f64 {
    let size = ss(t.s).unwrap_or(400).max(t.i as u64 + 1);
    t.s as f64 * SLOT_MS + (t.i as f64 / size as f64) * SLOT_MS
}

/// rp.structure, exactly
pub fn structure(tr: &[T], c: &LaunchInfo) -> Structure {
    let mut ins: HashSet<String> = HashSet::new();
    let creator = c.creator.clone().or_else(|| c.signer.clone());
    if let Some(x) = &creator { ins.insert(x.clone()); }
    if let Some(x) = &c.signer { ins.insert(x.clone()); }
    let (mut g_end, mut prev, mut glued) = (0usize, c.idx.map(|v| v as i64), Vec::<&T>::new());
    for (k, t) in tr.iter().enumerate() {
        if t.sig == c.sig { g_end = k + 1; continue; }
        if t.s == c.slot && prev.is_some() && (t.i as i64 == prev.unwrap() || t.i as i64 == prev.unwrap() + 1) && t.buy {
            glued.push(t); prev = Some(t.i as i64); g_end = k + 1;
        } else if t.s == c.slot && prev.is_some() && t.i as i64 > prev.unwrap() + 1 { break; }
        else if t.s > c.slot { break; }
    }
    for t in &glued { ins.insert(t.user.clone()); }
    Structure { g_end, glued: glued.len(), insiders: ins }
}

/// rp.repair_gaps: where a trade's pre-state differs from the previous post-state on the constant product (a lost trade),
/// insert a synthetic net trade before it
pub fn repair_gaps(tr: Vec<T>) -> Vec<T> {
    let mut out: Vec<T> = Vec::with_capacity(tr.len());
    let mut prev: Option<(u64, u64)> = None;
    for t in tr {
        let pre = if t.buy { (t.vsol.wrapping_sub(t.sol), t.vtok + t.tok) } else { (t.vsol + t.sol, t.vtok.wrapping_sub(t.tok)) };
        if let Some(p) = prev {
            if pre != p && t.vtok != 0 && p.1 != 0 {
                let dv = pre.0 as i128 - p.0 as i128; let dt = pre.1 as i128 - p.1 as i128;
                let ratio = (pre.0 as f64 * pre.1 as f64) / (p.0 as f64 * p.1 as f64);
                if dt != 0 && dv.abs() > 1000 && (ratio - 1.0).abs() < 0.002 {
                    out.push(T { j: -1, sig: format!("gap:{}", t.sig), user: "?".into(), buy: dv > 0, sol: dv.unsigned_abs() as u64, tok: dt.unsigned_abs() as u64,
                                 vsol: pre.0, vtok: pre.1, syn: true, ..t.clone() });
                }
            }
        }
        prev = Some((t.vsol, t.vtok));
        out.push(t);
    }
    out
}

/// the dump-event rules of the study builder (selbuild `work`, DIP_BUSY=0): a non-synthetic sell >= 1 SOL after the glued
/// bundle, token age 1 s .. `max_age_s`, curve < 100 SOL, the first such sell of its slot. Returns the trade indices.
pub fn dump_events(tr: &[T], c: &LaunchInfo, st: &Structure, max_age_s: f64) -> Vec<usize> {
    let mut out = Vec::new(); let mut busy: i64 = -1;
    for (k, t) in tr.iter().enumerate() {
        if t.buy || t.sol < MIN_SELL || t.syn || k < st.g_end { continue; }
        let age = (t.s as f64 - c.slot as f64) * SLOT_MS / 1000.0;
        if age < 1.0 || age > max_age_s || t.vsol >= 100_000_000_000 || t.s as i64 <= busy { continue; }
        out.push(k); busy = t.s as i64;
    }
    out
}

/// the launch-level filters of the builder (non-standard curves): Python uses the whole tape; a live engine calls it with
/// the tape so far
pub fn launch_ok(tr: &[T], c: &LaunchInfo) -> bool {
    if tr.is_empty() || c.mayhem { return false; }
    if tr.iter().map(|t| t.vsol).min().unwrap_or(0) < 25_000_000_000 { return false; }
    if tr.iter().take(50).map(|t| t.vsol).max().unwrap_or(0) > 200_000_000_000 { return false; }
    true
}

/// the three wallets' first buy within 1000 ms after the dump at k (block-position ms), before the next big sell:
/// selbuild's label (wallet prefix, delay ms)
pub fn labels(tr: &[T], k: usize, targets: &HashSet<String>, ss: &dyn Fn(u64) -> Option<u64>) -> Vec<(String, f64)> {
    let a0 = arr(&tr[k], ss); let mut out: Vec<(String, f64)> = Vec::new();
    for x in tr.iter().skip(k + 1).take(599) {
        if arr(x, ss) > a0 + 1000.0 || (!x.buy && x.sol >= MIN_SELL) { break; }
        if x.buy && targets.contains(&x.user) {
            let w8: String = x.user.chars().take(8).collect();
            if !out.iter().any(|(w, _)| *w == w8) { out.push((w8, rnd(arr(x, ss) - a0, 1))); }
        }
    }
    out
}

/// The 42 IMIT1 features of the dump tr[k] (FEATURES order), from trades up to and including the dump only.
/// `tgt_past`: arrival times (age ms + delay) of the three wallets' dip buys after EARLIER dump events of this token.
/// Caller guarantees: tr[k] is a dump event (see `dump_events`) and st.g_end >= 1.
pub fn features(tr: &[T], k: usize, c: &LaunchInfo, st: &Structure, cohort: &HashSet<String>, tgt_past: &[f64], ss: &dyn Fn(u64) -> Option<u64>) -> [f64; 42] {
    let t = &tr[k]; let s0 = c.slot;
    let ge = &tr[st.g_end - 1]; let pbp = px(ge);
    let a0 = arr(t, ss);
    let p_before = (t.vsol + t.sol) as f64 / (t.vtok - t.tok) as f64; let p_after = px(t);
    let (f_sol, f_vsol) = (t.sol, t.vsol);
    let pre = &tr[..k];
    let w20: Vec<&T> = tr[k.saturating_sub(60)..k].iter().filter(|x| t.s - x.s <= 20).collect();
    let peak = pre.iter().map(px).chain(std::iter::once(p_after)).fold(f64::MIN, f64::max);
    let sb: Vec<&T> = pre.iter().filter(|x| x.user == t.user).collect();
    let s_tok_b: u64 = sb.iter().filter(|x| x.buy).map(|x| x.tok).sum(); let s_tok_s: u64 = sb.iter().filter(|x| !x.buy).map(|x| x.tok).sum();
    let s_sol_b: u64 = sb.iter().filter(|x| x.buy).map(|x| x.sol).sum(); let s_sol_s: u64 = sb.iter().filter(|x| !x.buy).map(|x| x.sol).sum::<u64>() + f_sol;
    let held = (s_tok_b as i128 - s_tok_s as i128).max(1) as f64;
    let fb = sb.iter().find(|x| x.buy);
    let big_before: Vec<&T> = tr[st.g_end..k].iter().filter(|x| !x.buy && x.sol >= MIN_SELL).collect();
    let j5 = (0..k).rev().find(|&j| t.s - tr[j].s >= 5); let j20 = (0..k).rev().find(|&j| t.s - tr[j].s >= 20);
    let w3: Vec<&T> = tr[k.saturating_sub(30)..k].iter().filter(|x| t.s - x.s <= 3).collect();
    let insb: u64 = pre.iter().filter(|x| x.buy && st.insiders.contains(&x.user)).map(|x| x.tok).sum();
    let inss: u64 = pre.iter().filter(|x| !x.buy && st.insiders.contains(&x.user)).map(|x| x.tok).sum();
    let ins = st.insiders.contains(&t.user);
    // row-level
    let age = rnd((t.s as f64 - s0 as f64) * SLOT_MS / 1000.0, 2);
    let sell = rnd(f_sol as f64 / 1e9, 3);
    let drop = rnd(p_after / p_before, 4);
    let vsol = rnd(f_vsol as f64 / 1e9, 2);
    let nb = pre.iter().filter(|x| x.buy).count() as f64; let ns = pre.iter().filter(|x| !x.buy).count() as f64;
    let pb = rnd(p_after / pbp, 4); let dd = rnd(p_after / peak, 4);
    let b20 = rnd(w20.iter().filter(|x| x.buy).map(|x| x.sol).sum::<u64>() as f64 / 1e9, 3);
    let s20 = rnd(w20.iter().filter(|x| !x.buy).map(|x| x.sol).sum::<u64>() as f64 / 1e9, 3);
    let u20 = w20.iter().filter(|x| x.buy).map(|x| x.user.as_str()).collect::<HashSet<_>>().len() as f64;
    let dev = rnd(tr[..st.g_end].iter().filter(|x| x.buy).map(|x| x.sol).sum::<u64>() as f64 / 1e9, 3);
    let first_big = if big_before.is_empty() { 1.0 } else { 0.0 };
    // xf
    let s_frac = rnd((t.tok as f64 / held).min(2.0), 3);
    let s_pnl = rnd((s_sol_s as f64 - s_sol_b as f64) / 1e9, 3);
    let s_nb = sb.iter().filter(|x| x.buy).count() as f64;
    let s_entry = fb.map(|x| x.s as f64 - s0 as f64).unwrap_or(-1.0);
    let n_big = big_before.len() as f64;
    let since_big = big_before.last().map(|x| (t.s - x.s) as f64).unwrap_or(999.0);
    let ret5 = j5.map(|j| rnd(p_before / px(&tr[j]), 4)).unwrap_or(1.0);
    let ret20 = j20.map(|j| rnd(p_before / px(&tr[j]), 4)).unwrap_or(1.0);
    let peak_mult = rnd(peak / pbp, 4);
    let b3 = rnd(w3.iter().filter(|x| x.buy).map(|x| x.sol).sum::<u64>() as f64 / 1e9, 3);
    let nb3 = w3.iter().filter(|x| x.buy).count() as f64;
    let sellers20 = w20.iter().filter(|x| !x.buy).map(|x| x.user.as_str()).collect::<HashSet<_>>().len() as f64;
    let uniq_buyers = pre.iter().filter(|x| x.buy).map(|x| x.user.as_str()).collect::<HashSet<_>>().len() as f64;
    let ins_sold = if insb > 0 { rnd(inss as f64 / insb as f64, 3) } else { 0.0 };
    let net_flow = rnd((pre.iter().filter(|x| x.buy).map(|x| x.sol).sum::<u64>() as f64 - pre.iter().filter(|x| !x.buy).map(|x| x.sol).sum::<u64>() as f64) / 1e9, 3);
    let slotpos = rnd(t.i as f64 / ss(t.s).unwrap_or(400).max(t.i as u64 + 1) as f64, 3);
    // token facts
    let prev_sell_ms = match pre.iter().rev().find(|x| !x.buy && x.sol >= MIN_SELL) { Some(p) => rnd(a0 - arr(p, ss), 1), None => 1e9 };
    let n_tr = k as f64;
    let vmax = rnd(tr[..=k].iter().map(|x| x.vsol).max().unwrap_or(0) as f64 / 1e9, 2);
    let since_buy = match pre.iter().rev().find(|x| x.buy) { Some(lb) => { let v = rnd((a0 - arr(lb, ss)) / 1000.0, 3); if v >= 0.0 { v } else { 1e9 } } None => 1e9 };
    // the three wallets' earlier dip buys on this token
    let t0 = rnd(age, 2) * 1000.0;
    let before: Vec<f64> = tgt_past.iter().copied().filter(|b| *b < t0).collect();
    let tgt_n = before.len() as f64;
    let tgt_since = before.iter().copied().fold(f64::MIN, f64::max);
    let tgt_since = if before.is_empty() { 1e9 } else { (t0 - tgt_since) / 1000.0 };
    // the profitable-bot cohort (TRAIN-hours list): buyers so far, buyers in the last 20 slots, seller, SOL bought, still holding
    let mut cb: HashSet<&str> = HashSet::new(); let mut coh_sol: u64 = 0; let mut bal: HashMap<&str, i128> = HashMap::new();
    for x in pre {
        if !cohort.contains(&x.user) { continue; }
        if x.buy { cb.insert(x.user.as_str()); coh_sol += x.sol; *bal.entry(x.user.as_str()).or_default() += x.tok as i128; }
        else { *bal.entry(x.user.as_str()).or_default() -= x.tok as i128; }
    }
    let adj = if cohort.contains(&t.user) { t.tok as i128 } else { 0 };
    let coh_held = cb.iter().filter(|u| bal.get(*u).copied().unwrap_or(0) - if **u == t.user.as_str() { adj } else { 0 } > 0).count() as f64;
    let coh_20 = w20.iter().filter(|x| x.buy && cohort.contains(&x.user)).map(|x| x.user.as_str()).collect::<HashSet<_>>().len() as f64;
    let coh_seller = if cohort.contains(&t.user) { 1.0 } else { 0.0 };
    [age, sell, (1.0 - drop) * 100.0, vsol, pb, dd, nb, ns, b20, s20, u20, dev, st.glued as f64, first_big, if ins { 1.0 } else { 0.0 },
     s_frac, s_pnl, s_nb, s_entry, n_big, since_big, ret5, ret20, peak_mult, b3, nb3, sellers20, uniq_buyers, ins_sold, net_flow, slotpos,
     prev_sell_ms, n_tr, vmax, since_buy, tgt_n, tgt_since, cb.len() as f64, coh_20, coh_seller, rnd(coh_sol as f64 / 1e9, 3), coh_held]
}

/// the frozen selector: GBDT + watch envelope + tier thresholds + exits (sel/IMIT1.json)
pub struct Imit {
    pub g: Gbdt,
    /// (feature index, ">=" true / "<=" false, value)
    pub envelope: Vec<(usize, bool, f64)>,
    pub thresholds: HashMap<String, f64>,
    /// tier -> (take-profit, stop-loss, time limit slots, min hold slots) as fractions / slots
    pub exits: HashMap<String, (f64, f64, u64, u64)>,
}

impl Imit {
    pub fn load(path: &str) -> Result<Imit, String> {
        let s = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
        let v: serde_json::Value = serde_json::from_str(&s).map_err(|e| format!("{path}: {e}"))?;
        let g = Gbdt::from_json(&v)?;
        if g.features.len() != FEATURES.len() || g.features.iter().zip(FEATURES.iter()).any(|(a, b)| a != b) { return Err(format!("{path}: feature order differs from dip_imit::FEATURES")); }
        let mut envelope = Vec::new();
        for e in v["envelope"].as_array().ok_or("no envelope")? {
            let a = e.as_array().ok_or("bad envelope row")?;
            let name = a[0].as_str().ok_or("bad envelope feature")?;
            let j = FEATURES.iter().position(|f| *f == name).ok_or_else(|| format!("unknown envelope feature {name}"))?;
            envelope.push((j, a[1].as_str() == Some(">="), a[2].as_f64().ok_or("bad envelope value")?));
        }
        let mut exits = HashMap::new();
        if let Some(o) = v["exits"].as_object() {
            for (tier, x) in o {
                let a = x.as_array().ok_or("bad exit")?;
                exits.insert(tier.clone(), (a[1].as_f64().unwrap_or(9.0), a[2].as_f64().unwrap_or(9.0), a[3].as_u64().unwrap_or(6), a[4].as_u64().unwrap_or(1)));
            }
        }
        Ok(Imit { thresholds: g.thresholds.clone(), g, envelope, exits })
    }
    pub fn in_envelope(&self, x: &[f64; 42]) -> bool { self.envelope.iter().all(|&(j, ge, v)| if ge { x[j] >= v } else { x[j] <= v }) }
    pub fn score(&self, x: &[f64; 42]) -> f64 { self.g.score(x) }

    /// SHRED FIRE (dip14): the envelope when every feature j may be anywhere in [lo[j], hi[j]]: Some(true) = in for every value,
    /// Some(false) = out for every value, None = it depends (each condition is a threshold, so its two ends decide)
    pub fn envelope_bounds(&self, lo: &[f64; 42], hi: &[f64; 42]) -> Option<bool> {
        let (mut all_in, mut any_out_for_sure) = (true, false);
        for &(j, ge, v) in &self.envelope {
            let (a, b) = (lo[j].min(hi[j]), lo[j].max(hi[j]));
            let (sure_in, sure_out) = if ge { (a >= v, b < v) } else { (b <= v, a > v) };
            if !sure_in { all_in = false; }
            if sure_out { any_out_for_sure = true; }
        }
        if any_out_for_sure { Some(false) } else if all_in { Some(true) } else { None }
    }

    /// SHRED FIRE (dip14): (lowest, highest) score over the same intervals (`Gbdt::score_bounds`)
    pub fn score_bounds(&self, lo: &[f64; 42], hi: &[f64; 42]) -> (f64, f64) { self.g.score_bounds(lo, hi) }
}

/// SHRED FIRE (dip14): the IMIT1 features that depend on the dump's tx index in its block (the only input a shred feed does not
/// give): slotpos, prev_sell_ms and since_buy (FEATURES 30, 31, 34). Each is non-decreasing in the index.
pub const TIME_FEATS: [usize; 3] = [30, 31, 34];

/// SHRED FIRE (dip14): those three features of the dump tr[k] as if its tx index were `i` (the rest of tr[k] as it is), computed
/// exactly as `features` does (same expressions, same rounding). Caller: tr[k] is the newest trade and i > the index of every
/// earlier trade of its slot.
pub fn time_feats(tr: &[T], k: usize, i: u32, ss: &dyn Fn(u64) -> Option<u64>) -> [f64; 3] {
    let t = &tr[k];
    let size = ss(t.s).unwrap_or(400).max(i as u64 + 1);
    let a0 = t.s as f64 * SLOT_MS + (i as f64 / size as f64) * SLOT_MS;
    let pre = &tr[..k];
    let slotpos = rnd(i as f64 / size as f64, 3);
    let prev_sell_ms = match pre.iter().rev().find(|x| !x.buy && x.sol >= MIN_SELL) { Some(p) => rnd(a0 - arr(p, ss), 1), None => 1e9 };
    let since_buy = match pre.iter().rev().find(|x| x.buy) { Some(lb) => { let v = rnd((a0 - arr(lb, ss)) / 1000.0, 3); if v >= 0.0 { v } else { 1e9 } } None => 1e9 };
    [slotpos, prev_sell_ms, since_buy]
}

#[cfg(test)]
mod tests {
    use super::*;
    fn load_json(p: &str) -> Option<serde_json::Value> { std::fs::read_to_string(p).ok().and_then(|s| serde_json::from_str(&s).ok()) }

    #[test]
    fn imit1_parity_with_python() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(par) = load_json(&format!("{root}/testdata/imit1_parity.json")) else { eprintln!("imit1_parity.json missing: skipped"); return; };
        let model = Imit::load(&format!("{root}/ops/overnight/sel/IMIT1.json")).or_else(|_| Imit::load("/home/moiz/sniper/ops/overnight/sel/IMIT1.json"));
        let Ok(model) = model else { eprintln!("IMIT1.json missing: skipped"); return; };
        let cohort: HashSet<String> = par["cohort"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
        let targets: HashSet<String> = par["targets"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
        let max_age = par["max_age"].as_f64().unwrap();
        let (mut n, mut feat_bad, mut score_bad, mut ev_bad, mut lab_bad, mut worst) = (0usize, 0usize, 0usize, 0usize, 0usize, 0f64);
        let mut per_feat = vec![0usize; 42];
        for tk in par["tokens"].as_array().unwrap() {
            let tr: Vec<T> = tk["trades"].as_array().unwrap().iter().map(|r| T {
                s: r["s"].as_u64().unwrap(), i: r["i"].as_u64().unwrap() as u32, j: r["j"].as_i64().unwrap() as i32, sig: r["sig"].as_str().unwrap().to_string(),
                user: r["user"].as_str().unwrap().to_string(), buy: r["buy"].as_bool().unwrap(), sol: r["sol"].as_u64().unwrap(), tok: r["tok"].as_u64().unwrap(),
                vsol: r["vsol"].as_u64().unwrap(), vtok: r["vtok"].as_u64().unwrap(), fbps: r["fbps"].as_u64().unwrap_or(95) as u32, cbps: r["cbps"].as_u64().unwrap_or(30) as u32,
                syn: r["syn"].as_bool().unwrap() }).collect();
            let la = &tk["launch"];
            let c = LaunchInfo { slot: la["slot"].as_u64().unwrap(), idx: la["idx"].as_u64().map(|v| v as u32), creator: la["creator"].as_str().map(|s| s.to_string()),
                                 signer: la["user"].as_str().map(|s| s.to_string()), sig: la["sig"].as_str().unwrap_or("").to_string(), mayhem: la["mayhem"].as_bool().unwrap_or(false) };
            let ssm: HashMap<u64, u64> = tk["ss"].as_object().unwrap().iter().map(|(k, v)| (k.parse().unwrap(), v.as_u64().unwrap())).collect();
            let ss = |s: u64| ssm.get(&s).copied();
            let st = structure(&tr, &c);
            assert!(launch_ok(&tr, &c), "launch filter on {}", tk["mint"]);
            let evs = dump_events(&tr, &c, &st, max_age);
            let want: Vec<usize> = tk["events"].as_array().unwrap().iter().map(|e| e["k"].as_u64().unwrap() as usize).collect();
            if evs != want { ev_bad += 1; if ev_bad <= 3 { eprintln!("event set differs on {}: rust {:?} python {:?}", tk["mint"], evs, want); } }
            let mut past: Vec<f64> = Vec::new();
            for e in tk["events"].as_array().unwrap() {
                let k = e["k"].as_u64().unwrap() as usize;
                let x = features(&tr, k, &c, &st, &cohort, &past, &ss);
                let py: Vec<f64> = e["feats"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
                n += 1;
                let bad: Vec<usize> = (0..42).filter(|&j| (x[j] - py[j]).abs() > 1e-9 * (1.0 + py[j].abs())).collect();
                for &j in &bad { per_feat[j] += 1; }
                if !bad.is_empty() { feat_bad += 1; if feat_bad <= 5 { eprintln!("feature mismatch {} k={k}: {:?}", tk["mint"], bad.iter().map(|&j| (FEATURES[j], x[j], py[j])).collect::<Vec<_>>()); } }
                let d = (model.score(&x) - e["score"].as_f64().unwrap()).abs(); worst = worst.max(d);
                if d > 1e-9 { score_bad += 1; }
                // labels -> the next events' tgt features (the Python's own labels drive the parity; ours must equal them)
                let lab_py: HashMap<String, f64> = e["lab"].as_object().unwrap().iter().map(|(w, d)| (w.clone(), d.as_f64().unwrap())).collect();
                let lab_rs = labels(&tr, k, &targets, &ss);
                if lab_rs.len() != lab_py.len() || lab_rs.iter().any(|(w, d)| lab_py.get(w).map(|p| (p - d).abs() > 0.051).unwrap_or(true)) { lab_bad += 1; }
                let t0 = e["age"].as_f64().unwrap() * 1000.0;
                for d in lab_py.values() { past.push(t0 + d); }
            }
        }
        eprintln!("imit1 parity: {n} events, event-set mismatches {ev_bad}, feature mismatches {feat_bad}, label mismatches {lab_bad}, score mismatches {score_bad}, worst score diff {worst:e}");
        eprintln!("  mismatches per feature: {:?}", (0..42).filter(|&j| per_feat[j] > 0).map(|j| (FEATURES[j], per_feat[j])).collect::<Vec<_>>());
        assert!(n > 1000, "too few parity events");
        assert!(feat_bad * 200 <= n, "more than 0.5% of events have a feature mismatch");
        assert!(score_bad * 200 <= n, "more than 0.5% of events have a score mismatch");
        assert!(ev_bad * 100 <= par["tokens"].as_array().unwrap().len(), "event sets differ on more than 1% of tokens");
    }
}

// ---- the live book: one token's state as executed transactions stream in (the dip engine, ops/dip/ENGINE_IMIT1.md) ----

/// a dump the book found, with its features and score (the engine decides from these)
#[derive(Clone, Debug)]
pub struct Dump { pub mint: String, pub k: usize, pub age: f64, pub feats: [f64; 42], pub score: f64, pub env_ok: bool, pub launch_ok: bool }

/// one watched token: launch facts, the trade tape (chain order, gap-repaired as rp.repair_gaps), the dump events, the three
/// wallets' dip-buy times after earlier dumps (tgt features), and the open label window (the latest dump, 1000 ms, closed
/// by the next big sell)
pub struct TokenBook {
    pub c: LaunchInfo,
    pub tr: Vec<T>,
    pub busy: i64,
    pub events: Vec<usize>,
    pub tgt_past: Vec<f64>,
    /// (dump trade index, its block-position arrival ms, its age ms, wallets already labeled)
    window: Option<(usize, f64, f64, Vec<String>)>,
}

/// SHRED FIRE (dip14): a TokenBook's state before a speculative `push` of a newer trade (`TokenBook::checkpoint`); `rollback` puts
/// the book back exactly (a push of the NEWEST trade only appends: an optional gap-repair trade + the trade, the dump-event state
/// and the label window)
#[derive(Clone, Debug)]
pub struct BookCkpt { n: usize, busy: i64, events: usize, tgt: usize, window: Option<(usize, f64, f64, Vec<String>)> }

impl TokenBook {
    pub fn new(c: LaunchInfo) -> TokenBook { TokenBook { c, tr: Vec::new(), busy: -1, events: Vec::new(), tgt_past: Vec::new(), window: None } }

    /// SHRED FIRE (dip14): the chain key (slot, tx index, event index) of the newest trade
    pub fn last_key(&self) -> Option<(u64, u32, i32)> { self.tr.last().map(|x| (x.s, x.i, x.j)) }

    /// SHRED FIRE (dip14): the state a speculative push of a trade NEWER than every trade in the book can be undone to
    pub fn checkpoint(&self) -> BookCkpt {
        BookCkpt { n: self.tr.len(), busy: self.busy, events: self.events.len(), tgt: self.tgt_past.len(), window: self.window.clone() }
    }

    /// SHRED FIRE (dip14): undo everything since `c` (only valid when the pushes since were of newer trades: they appended)
    pub fn rollback(&mut self, c: BookCkpt) {
        self.tr.truncate(c.n);
        self.busy = c.busy;
        self.events.truncate(c.events);
        self.tgt_past.truncate(c.tgt);
        self.window = c.window;
    }

    /// add one executed trade (in chain order per token: slot, tx index, event index). Returns the dump index when the trade
    /// is a dump event (selbuild rules) and the features can be computed. Out-of-order trades are inserted in place (the
    /// tape stays sorted) but never trigger: the engine decides only on the newest trade.
    pub fn push(&mut self, t: T, targets: &HashSet<String>, max_age_s: f64, ss: &dyn Fn(u64) -> Option<u64>) -> Option<usize> {
        let key = (t.s, t.i, t.j);
        if let Some(last) = self.tr.last() {
            if (last.s, last.i, last.j) > key {
                let pos = self.tr.partition_point(|x| (x.s, x.i, x.j) < key);
                if self.tr.get(pos).map(|x| (x.s, x.i, x.j) == key).unwrap_or(false) { return None; }  // duplicate
                self.tr.insert(pos, t);
                return None;
            }
            if (last.s, last.i, last.j) == key { return None; }
        }
        // rp.repair_gaps on the newest trade
        if let Some(p) = self.tr.iter().rev().find(|x| true).map(|x| (x.vsol, x.vtok)) {
            let pre = if t.buy { (t.vsol.wrapping_sub(t.sol), t.vtok + t.tok) } else { (t.vsol + t.sol, t.vtok.wrapping_sub(t.tok)) };
            if pre != p && t.vtok != 0 && p.1 != 0 {
                let dv = pre.0 as i128 - p.0 as i128; let dt = pre.1 as i128 - p.1 as i128;
                let ratio = (pre.0 as f64 * pre.1 as f64) / (p.0 as f64 * p.1 as f64);
                if dt != 0 && dv.abs() > 1000 && (ratio - 1.0).abs() < 0.002 {
                    self.tr.push(T { j: -1, sig: format!("gap:{}", t.sig), user: "?".into(), buy: dv > 0, sol: dv.unsigned_abs() as u64, tok: dt.unsigned_abs() as u64,
                                     vsol: pre.0, vtok: pre.1, syn: true, ..t.clone() });
                }
            }
        }
        self.tr.push(t);
        let k = self.tr.len() - 1;
        // label window of the latest dump (selbuild `lab`): closes after 1000 ms or at the next big sell
        let x = &self.tr[k];
        if let Some((wk, a0, age_ms, labeled)) = self.window.as_mut() {
            let ax = arr(x, ss);
            if k <= *wk { }
            else if ax > *a0 + 1000.0 || (!x.buy && x.sol >= MIN_SELL) { self.window = None; }
            else if x.buy && targets.contains(&x.user) {
                let w8: String = x.user.chars().take(8).collect();
                if !labeled.contains(&w8) { labeled.push(w8); let d = rnd(ax - *a0, 1); self.tgt_past.push(*age_ms + d); }
            }
        }
        // dump event?
        let t = &self.tr[k];
        if t.buy || t.sol < MIN_SELL || t.syn { return None; }
        let st = structure(&self.tr, &self.c);
        if k < st.g_end || st.g_end < 1 { return None; }
        let age = (t.s as f64 - self.c.slot as f64) * SLOT_MS / 1000.0;
        if age < 1.0 || age > max_age_s || t.vsol >= 100_000_000_000 || t.s as i64 <= self.busy { return None; }
        self.busy = t.s as i64; self.events.push(k);
        self.window = Some((k, arr(t, ss), rnd(age, 2) * 1000.0, Vec::new()));
        Some(k)
    }

    /// M2 (dip_model, --dip-m2): the newest trade's index when it is the trade `key` and a big sell that is NOT a dump event
    /// only because an earlier big sell of the same slot already was one (these rules take the first per slot; the M2 study's
    /// Stage A replay sees every dump). Otherwise the same rules as `push`. Read-only: the book is unchanged.
    pub fn later_in_slot(&self, key: (u64, u32, i32), max_age_s: f64) -> Option<usize> {
        let k = self.tr.len().checked_sub(1)?;
        let t = &self.tr[k];
        if (t.s, t.i, t.j) != key || t.buy || t.sol < MIN_SELL || t.syn || t.s as i64 != self.busy || self.events.last() == Some(&k) { return None; }
        let st = structure(&self.tr, &self.c);
        if k < st.g_end || st.g_end < 1 { return None; }
        let age = (t.s as f64 - self.c.slot as f64) * SLOT_MS / 1000.0;
        if age < 1.0 || age > max_age_s || t.vsol >= 100_000_000_000 { return None; }
        Some(k)
    }

    /// the features, score and envelope check of the dump at k
    pub fn dump(&self, mint: &str, k: usize, model: &Imit, cohort: &HashSet<String>, ss: &dyn Fn(u64) -> Option<u64>) -> Dump {
        let st = structure(&self.tr, &self.c);
        // tgt features see only dip buys recorded before this dump (the window of this dump opened after them)
        let feats = features(&self.tr, k, &self.c, &st, cohort, &self.tgt_past, ss);
        Dump { mint: mint.to_string(), k, age: feats[0], score: model.score(&feats), env_ok: model.in_envelope(&feats), feats, launch_ok: launch_ok(&self.tr, &self.c) }
    }
}

#[cfg(test)]
mod book_tests {
    use super::*;

    /// the live book, fed the parity tapes one trade at a time (synthetic trades stripped: the book repairs gaps itself), must
    /// find the same dumps with the same features and scores as the batch port (which equals the Python)
    #[test]
    fn live_book_equals_batch() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(par) = std::fs::read_to_string(format!("{root}/testdata/imit1_parity.json")).ok().and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok()) else { return; };
        let Ok(model) = Imit::load("/home/moiz/sniper/ops/overnight/sel/IMIT1.json") else { return; };
        let cohort: HashSet<String> = par["cohort"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
        let targets: HashSet<String> = par["targets"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
        let max_age = par["max_age"].as_f64().unwrap();
        let (mut n, mut bad, mut missing, mut extra, mut flips_noss, mut picks) = (0usize, 0usize, 0usize, 0usize, 0usize, 0usize);
        let thr = model.thresholds["top4"];
        for tk in par["tokens"].as_array().unwrap() {
            let la = &tk["launch"];
            let c = LaunchInfo { slot: la["slot"].as_u64().unwrap(), idx: la["idx"].as_u64().map(|v| v as u32), creator: la["creator"].as_str().map(|s| s.to_string()),
                                 signer: la["user"].as_str().map(|s| s.to_string()), sig: la["sig"].as_str().unwrap_or("").to_string(), mayhem: false };
            let ssm: HashMap<u64, u64> = tk["ss"].as_object().unwrap().iter().map(|(k, v)| (k.parse().unwrap(), v.as_u64().unwrap())).collect();
            let ss = |s: u64| ssm.get(&s).copied(); let none = |_s: u64| None;
            let mut b = TokenBook::new(c.clone()); let mut b0 = TokenBook::new(c.clone());
            let want: HashMap<usize, f64> = tk["events"].as_array().unwrap().iter().map(|e| (e["k"].as_u64().unwrap() as usize, e["score"].as_f64().unwrap())).collect();
            let mut got: HashMap<usize, f64> = HashMap::new();
            for r in tk["trades"].as_array().unwrap() {
                if r["syn"].as_bool().unwrap() { continue; }
                let t = T { s: r["s"].as_u64().unwrap(), i: r["i"].as_u64().unwrap() as u32, j: r["j"].as_i64().unwrap() as i32, sig: r["sig"].as_str().unwrap().to_string(),
                            user: r["user"].as_str().unwrap().to_string(), buy: r["buy"].as_bool().unwrap(), sol: r["sol"].as_u64().unwrap(), tok: r["tok"].as_u64().unwrap(),
                            vsol: r["vsol"].as_u64().unwrap(), vtok: r["vtok"].as_u64().unwrap(), fbps: 95, cbps: 30, syn: false };
                if let Some(k) = b.push(t.clone(), &targets, max_age, &ss) { let d = b.dump("m", k, &model, &cohort, &ss); got.insert(k, d.score); }
                if let Some(k) = b0.push(t, &targets, max_age, &none) {
                    let d0 = b0.dump("m", k, &model, &cohort, &none);
                    if let Some(&s) = want.get(&k) { if (s >= thr) != (d0.score >= thr) { flips_noss += 1; } }
                }
            }
            for (k, s) in &want {
                n += 1; if *s >= thr { picks += 1; }
                match got.get(k) { None => missing += 1, Some(g) => if (g - s).abs() > 1e-9 { bad += 1; } }
            }
            extra += got.keys().filter(|k| !want.contains_key(k)).count();
        }
        eprintln!("live book: {n} dumps, missing {missing}, extra {extra}, score mismatches {bad} | top-4% picks {picks}; decisions flipped without block sizes: {flips_noss}");
        assert!(missing == 0 && extra == 0 && bad == 0, "the live book differs from the batch port");
    }

    /// SHRED FIRE (dip14): on the parity tapes, before every real trade the book takes a SPECULATIVE push of that trade at another
    /// tx index and is rolled back: (1) the book is then exactly as before (every field), (2) the dumps found with the speculative
    /// pushes interleaved are the batch ones with the same scores, (3) time_feats at index i equals the features of a push at i,
    /// (4) the interval bounds over [i_lo, i_hi] contain the score at every probed index and equal it on a point interval
    #[test]
    fn spec_push_rollback_time_feats_bounds() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(par) = std::fs::read_to_string(format!("{root}/testdata/imit1_parity.json")).ok().and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok()) else { return; };
        let Ok(model) = Imit::load("/home/moiz/sniper/ops/overnight/sel/IMIT1.json") else { return; };
        let cohort: HashSet<String> = par["cohort"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
        let targets: HashSet<String> = par["targets"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
        let max_age = par["max_age"].as_f64().unwrap();
        let none = |_s: u64| None;
        let (mut n_spec, mut n_dumps, mut n_tf, mut n_bounds) = (0usize, 0usize, 0usize, 0usize);
        for tk in par["tokens"].as_array().unwrap() {
            let la = &tk["launch"];
            let c = LaunchInfo { slot: la["slot"].as_u64().unwrap(), idx: la["idx"].as_u64().map(|v| v as u32), creator: la["creator"].as_str().map(|s| s.to_string()),
                                 signer: la["user"].as_str().map(|s| s.to_string()), sig: la["sig"].as_str().unwrap_or("").to_string(), mayhem: false };
            let want: HashMap<usize, f64> = tk["events"].as_array().unwrap().iter().map(|e| (e["k"].as_u64().unwrap() as usize, e["score"].as_f64().unwrap())).collect();
            let mut b = TokenBook::new(c.clone());
            let mut reference = TokenBook::new(c.clone());
            let mut got: HashMap<usize, f64> = HashMap::new();
            let mut got_ref: HashMap<usize, f64> = HashMap::new();
            for r in tk["trades"].as_array().unwrap() {
                if r["syn"].as_bool().unwrap() { continue; }
                let t = T { s: r["s"].as_u64().unwrap(), i: r["i"].as_u64().unwrap() as u32, j: r["j"].as_i64().unwrap() as i32, sig: r["sig"].as_str().unwrap().to_string(),
                            user: r["user"].as_str().unwrap().to_string(), buy: r["buy"].as_bool().unwrap(), sol: r["sol"].as_u64().unwrap(), tok: r["tok"].as_u64().unwrap(),
                            vsol: r["vsol"].as_u64().unwrap(), vtok: r["vtok"].as_u64().unwrap(), fbps: 95, cbps: 30, syn: false };
                // the speculative push at a later index of the same slot (when newer than the book), then rollback
                let newer = b.last_key().is_none_or(|l| l < (t.s, t.i, t.j));
                if newer {
                    let before = (b.tr.clone(), b.busy, b.events.clone(), b.tgt_past.clone(), b.window.clone());
                    let ck = b.checkpoint();
                    let alt = T { i: t.i + 37, ..t.clone() };
                    let n0 = b.tr.len();
                    // (a push that needs a gap-repair trade gives it the pushed trade's index: the shred path never does, it prices the
                    // sell from the book's own newest state; the time features are checked on gap-free pushes)
                    if let Some(k) = b.push(alt, &targets, max_age, &none).filter(|_| b.tr.len() == n0 + 1) {
                        let d = b.dump("m", k, &model, &cohort, &none);
                        // time_feats at the alt index = the features; at the true index = the features of a push at the true index
                        let tf = time_feats(&b.tr, k, t.i + 37, &none);
                        for (n, &j) in TIME_FEATS.iter().enumerate() { assert_eq!(d.feats[j], tf[n], "time feature {j}"); }
                        let tf_true = time_feats(&b.tr, k, t.i, &none);
                        b.rollback(ck);
                        let ck2 = b.checkpoint();
                        let Some(k2) = b.push(t.clone(), &targets, max_age, &none) else { panic!("the same trade at its true index is not a dump") };
                        let d2 = b.dump("m", k2, &model, &cohort, &none);
                        for (n, &j) in TIME_FEATS.iter().enumerate() { assert_eq!(d2.feats[j], tf_true[n], "time feature {j} at the true index"); }
                        // every feature but the time ones is the same at both indexes
                        for j in (0..42).filter(|j| !TIME_FEATS.contains(j)) { assert_eq!(d.feats[j].to_bits(), d2.feats[j].to_bits(), "feature {j} moved with the index"); }
                        // bounds over [true i, true i + 37] contain both scores; a point interval is the score itself
                        let (lo, hi) = model.score_bounds(&d2.feats, &d.feats);
                        assert!(lo <= d2.score && d2.score <= hi && lo <= d.score && d.score <= hi, "bounds {lo}..{hi} miss {} / {}", d2.score, d.score);
                        assert_eq!(model.score_bounds(&d2.feats, &d2.feats), (d2.score, d2.score));
                        if let Some(e) = model.envelope_bounds(&d2.feats, &d.feats) { assert!(e == d.env_ok && e == d2.env_ok, "envelope bound {e} vs {} / {}", d.env_ok, d2.env_ok); }
                        if d.env_ok != d2.env_ok { assert_eq!(model.envelope_bounds(&d2.feats, &d.feats), None); }
                        n_tf += 1; n_bounds += 1;
                        b.rollback(ck2);
                    } else { b.rollback(ck); }
                    let after = (b.tr.clone(), b.busy, b.events.clone(), b.tgt_past.clone(), b.window.clone());
                    assert!(before.0 == after.0 && before.1 == after.1 && before.2 == after.2 && before.3 == after.3 && format!("{:?}", before.4) == format!("{:?}", after.4),
                        "rollback left the book changed");
                    n_spec += 1;
                }
                if let Some(k) = b.push(t.clone(), &targets, max_age, &none) { let d = b.dump("m", k, &model, &cohort, &none); got.insert(k, d.score); }
                if let Some(k) = reference.push(t, &targets, max_age, &none) { let d = reference.dump("m", k, &model, &cohort, &none); got_ref.insert(k, d.score); }
            }
            assert_eq!(b.tr, reference.tr);
            assert_eq!(got.iter().map(|(k, v)| (*k, v.to_bits())).collect::<std::collections::BTreeMap<_, _>>(),
                       got_ref.iter().map(|(k, v)| (*k, v.to_bits())).collect::<std::collections::BTreeMap<_, _>>(), "dumps differ from the book without speculative pushes");
            // the same dump events as the study (scores: no block sizes here, as the live engine; live_book_equals_batch checks them with)
            let mut a: Vec<usize> = got.keys().copied().collect(); a.sort();
            let mut w: Vec<usize> = want.keys().copied().collect(); w.sort();
            assert_eq!(a, w, "dump events");
            n_dumps += w.len();
        }
        eprintln!("spec push: {n_spec} speculative pushes rolled back exactly, {n_dumps} dumps unchanged, time features checked on {n_tf}, bounds on {n_bounds}");
        assert!(n_spec > 10_000 && n_tf > 500);
    }
}
