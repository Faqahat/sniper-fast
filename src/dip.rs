//! Dip-backrun selection (ops/dip/PLAN.md), standalone: the frozen GBDT (ops/overnight/dip/frozen_dip4_L*.json) and the 35
//! features at a big sell, ported line by line from ops/overnight/dip/dipbuy3.py (`work`) and dipcv.py (`fv`).
//! Not wired into the engine. Parity with the Python: `cargo test --lib dip` (testdata/dip_parity.json, exported by
//! ops/overnight/dip/export_parity.py).
use serde_json::Value;
use std::collections::{HashMap, HashSet};

/// rp.SLOT_MS
pub const SLOT_MS: f64 = 212.0;
/// a "big" sell: >= 1 SOL of curve SOL
pub const MIN_SELL: u64 = 1_000_000_000;

pub enum Node { Leaf(f64), Split { f: usize, b: i64, l: Box<Node>, r: Box<Node> } }

fn node(v: &Value) -> Result<Node, String> {
    if let Some(w) = v.get("w").and_then(|x| x.as_f64()) { return Ok(Node::Leaf(w)); }
    let f = v.get("f").and_then(|x| x.as_u64()).ok_or("tree node without f/w")? as usize;
    let b = v.get("b").and_then(|x| x.as_i64()).ok_or("tree node without b")?;
    Ok(Node::Split { f, b, l: Box::new(node(v.get("l").ok_or("no l")?)?), r: Box::new(node(v.get("r").ok_or("no r")?)?) })
}

/// numpy histogram GBDT (ops/overnight/dip/gbdt_np.py): bin = 0 for NaN, else #(edges <= x) + 1 (np.searchsorted side
/// "right" + 1); a split goes left when bin <= b; score = F0 + lr * sum(leaf weights)
pub struct Gbdt { pub name: String, pub features: Vec<String>, edges: Vec<Vec<f64>>, trees: Vec<Node>, f0: f64, lr: f64, pub thresholds: HashMap<String, f64> }

impl Gbdt {
    pub fn from_json(v: &Value) -> Result<Gbdt, String> {
        let features: Vec<String> = v["features"].as_array().ok_or("no features")?.iter().map(|x| x.as_str().unwrap_or("").to_string()).collect();
        let edges: Vec<Vec<f64>> = v["edges"].as_array().ok_or("no edges")?.iter()
            .map(|e| e.as_array().map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default()).collect();
        if edges.len() != features.len() { return Err(format!("{} edge lists for {} features", edges.len(), features.len())); }
        let trees = v["trees"].as_array().ok_or("no trees")?.iter().map(node).collect::<Result<Vec<_>, _>>()?;
        let thresholds = v["thresholds"].as_object().map(|o| o.iter().filter_map(|(k, x)| x.as_f64().map(|f| (k.clone(), f))).collect()).unwrap_or_default();
        Ok(Gbdt { name: v["name"].as_str().unwrap_or("?").to_string(), features, edges, trees, f0: v["F0"].as_f64().ok_or("no F0")?, lr: v["lr"].as_f64().ok_or("no lr")?, thresholds })
    }
    pub fn load(path: &str) -> Result<Gbdt, String> {
        let s = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
        Gbdt::from_json(&serde_json::from_str(&s).map_err(|e| format!("{path}: {e}"))?)
    }
    pub fn score(&self, x: &[f64]) -> f64 {
        let bins: Vec<i64> = x.iter().zip(self.edges.iter()).map(|(&v, e)| if v.is_nan() { 0 } else { e.partition_point(|&q| q <= v) as i64 + 1 }).collect();
        let mut f = self.f0;
        for t in &self.trees {
            let mut n = t;
            loop {
                match n {
                    Node::Leaf(w) => { f += self.lr * w; break; }
                    Node::Split { f: j, b, l, r } => { n = if bins[*j] <= *b { l } else { r }; }
                }
            }
        }
        f
    }
}

/// one curve trade of a launch, in chain order (rp.read_bucket + repair_gaps; synthetic gap trades have user "?")
#[derive(Clone, Debug)]
pub struct Trade { pub s: u64, pub i: u32, pub user: String, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64, pub syn: bool }

/// the launch context (rp.structure): create slot, end of the dev's glued bundle in the trade list, insiders, glued count
pub struct Launch { pub slot: u64, pub g_end: usize, pub insiders: HashSet<String>, pub glued: usize }

/// wallet tags: 8-char prefixes of the 321 snipers, 6-char prefixes of the 9 pros (frozen JSON "sn8" / "pro6")
pub struct Tags { pub sn8: HashSet<String>, pub pro6: Vec<String> }

/// Python's round(x, n): correctly rounded to n decimals (ties to even on the exact binary value), via Rust's formatter
fn rnd(x: f64, n: usize) -> f64 { format!("{:.*}", n, x).parse().unwrap_or(x) }
fn px(t: &Trade) -> f64 { t.vsol as f64 / t.vtok as f64 }

/// The 35 features of the sell tr[k], in the frozen model's order (dipcv.FK), from trades up to and including the sell only.
/// Caller guarantees: tr[k] is a non-synthetic sell, k >= l.g_end >= 1.
pub fn features(tr: &[Trade], k: usize, l: &Launch, tags: &Tags) -> Vec<f64> {
    let t = &tr[k];
    let ge = &tr[l.g_end - 1]; let pbp = px(ge);
    let age = rnd((t.s as f64 - l.slot as f64) * SLOT_MS / 1000.0, 2);
    let sell = rnd(t.sol as f64 / 1e9, 3);
    let p_before = (t.vsol + t.sol) as f64 / (t.vtok - t.tok) as f64; let p_after = px(t);
    let drop = rnd(p_after / p_before, 4);
    let vsol = rnd(t.vsol as f64 / 1e9, 2);
    let pre = &tr[..k];
    let nb = pre.iter().filter(|x| x.buy).count() as f64; let ns = pre.iter().filter(|x| !x.buy).count() as f64;
    let w20: Vec<&Trade> = tr[k.saturating_sub(60)..k].iter().filter(|x| t.s - x.s <= 20).collect();
    let peak = tr[..=k].iter().map(px).fold(f64::MIN, f64::max);
    let pb = rnd(p_after / pbp, 4); let dd = rnd(p_after / peak, 4);
    let b20 = rnd(w20.iter().filter(|x| x.buy).map(|x| x.sol).sum::<u64>() as f64 / 1e9, 3);
    let s20 = rnd(w20.iter().filter(|x| !x.buy).map(|x| x.sol).sum::<u64>() as f64 / 1e9, 3);
    let u20 = w20.iter().filter(|x| x.buy).map(|x| x.user.as_str()).collect::<HashSet<_>>().len() as f64;
    let dev = rnd(tr[..l.g_end].iter().filter(|x| x.buy).map(|x| x.sol).sum::<u64>() as f64 / 1e9, 3);
    let big_before: Vec<&Trade> = tr[l.g_end..k].iter().filter(|x| !x.buy && x.sol >= MIN_SELL).collect();
    let first_big = if big_before.is_empty() { 1.0 } else { 0.0 };
    let ins = l.insiders.contains(&t.user);
    let seller8: String = t.user.chars().take(8).collect();
    let pro_seller = if tags.pro6.iter().any(|p| seller8.starts_with(p.as_str())) { 1.0 } else { 0.0 };
    let snp_seller = if tags.sn8.contains(&seller8) { 1.0 } else { 0.0 };
    let sell_share = sell / (vsol - 30.0).max(0.1);
    let bs_ratio = b20 / (s20 + 0.1);
    // richer features
    let sb: Vec<&Trade> = pre.iter().filter(|x| x.user == t.user).collect();
    let s_tok_b: u64 = sb.iter().filter(|x| x.buy).map(|x| x.tok).sum(); let s_tok_s: u64 = sb.iter().filter(|x| !x.buy).map(|x| x.tok).sum();
    let s_sol_b: u64 = sb.iter().filter(|x| x.buy).map(|x| x.sol).sum(); let s_sol_s: u64 = sb.iter().filter(|x| !x.buy).map(|x| x.sol).sum::<u64>() + t.sol;
    let held = (s_tok_b as i128 - s_tok_s as i128).max(1) as f64;
    let fb = sb.iter().find(|x| x.buy);
    let j5 = (0..k).rev().find(|&j| t.s - tr[j].s >= 5); let j20 = (0..k).rev().find(|&j| t.s - tr[j].s >= 20);
    let w3: Vec<&Trade> = tr[k.saturating_sub(30)..k].iter().filter(|x| t.s - x.s <= 3).collect();
    let insb: u64 = pre.iter().filter(|x| x.buy && l.insiders.contains(&x.user)).map(|x| x.tok).sum();
    let inss: u64 = pre.iter().filter(|x| !x.buy && l.insiders.contains(&x.user)).map(|x| x.tok).sum();
    let s_frac = rnd((t.tok as f64 / held).min(2.0), 3);
    let s_pnl = rnd((s_sol_s as f64 - s_sol_b as f64) / 1e9, 3);
    let s_nb = sb.iter().filter(|x| x.buy).count() as f64;
    let s_entry = fb.map(|x| x.s as f64 - l.slot as f64).unwrap_or(-1.0);
    let s_in_bundle = if ins { 1.0 } else { 0.0 };
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
    vec![age, sell, drop, vsol, nb, ns, pb, dd, b20, s20, u20, dev, l.glued as f64, first_big, if ins { 1.0 } else { 0.0 }, pro_seller, snp_seller,
         sell_share, bs_ratio, s_frac, s_pnl, s_nb, s_entry, s_in_bundle, n_big, since_big, ret5, ret20, peak_mult, b3, nb3, sellers20, uniq_buyers,
         ins_sold, net_flow]
}

/// the feature names in `features` order (must equal the frozen model's "features")
pub const FEATURES: [&str; 35] = ["age", "sell", "drop", "vsol", "nb", "ns", "pb", "dd", "b20", "s20", "u20", "dev", "glued", "first_big", "ins",
    "pro_seller", "snp_seller", "sell_share", "bs_ratio", "s_frac", "s_pnl", "s_nb", "s_entry", "s_in_bundle", "n_big", "since_big", "ret5", "ret20",
    "peak_mult", "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold", "net_flow"];

// ---- live decoders for the dip engine (ops/dip/ENGINE_V1.md); not wired into the engine ----

use crate::tx::{Pk, Tx};

/// top-level pump sell layouts seen in dip triggers, as (discriminator, account position of the mint, of the seller); all
/// carry tokens to sell at data[8..16] and min SOL out at [16..24]. Validated on 800 real triggers against their TradeEvents
/// (ops/overnight/dipshadow/trig_decode.py): sell, sell_v3, and the 26/27-account sell.
pub const SELL_LAYOUTS: [([u8; 8], usize, usize); 3] = [
    ([0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad], 2, 6),
    ([0x1c, 0x92, 0xde, 0x77, 0x26, 0xc4, 0x69, 0xd5], 1, 8),
    ([0x5d, 0xf6, 0x82, 0x3c, 0xe7, 0xe9, 0x40, 0xb2], 1, 13),
];

/// one top-level pump sell as a shred feed sees it (before execution: it may still fail on chain)
#[derive(Clone, Debug, PartialEq)]
pub struct DirectSell { pub mint: Pk, pub seller: Pk, pub tokens: u64, pub min_sol: u64 }

/// account `i` of the full list: static keys, then the feed-resolved lookup addresses (writable, then readonly)
fn key_at(tx: &Tx, i: usize) -> Option<Pk> {
    if let Some(k) = tx.keys.get(i) { return Some(*k); }
    let (w, r) = tx.loaded.as_ref()?;
    let j = i - tx.keys.len();
    w.get(j).or_else(|| r.get(j.checked_sub(w.len())?)).copied()
}

/// every top-level pump sell in a tx, in instruction order. A tx dumping from several wallets returns several entries (sum
/// them per mint to price the dump). The seller comes from its account position, not the signer (they differ in ~3%).
/// A sell whose mint or seller sits behind an unresolved lookup table is skipped.
pub fn direct_sells(tx: &Tx) -> Vec<DirectSell> {
    let mut out = Vec::new();
    if tx.is_vote { return out; }
    for ix in &tx.ixs {
        if tx.keys.get(ix.program as usize) != Some(&*crate::snipe::PUMP) || ix.data.len() < 24 { continue; }
        let Some(&(_, mpos, spos)) = SELL_LAYOUTS.iter().find(|(d, _, _)| ix.data[..8] == d[..]) else { continue };
        let at = |p: usize| ix.accounts.get(p).and_then(|&a| key_at(tx, a as usize));
        let (Some(mint), Some(seller)) = (at(mpos), at(spos)) else { continue };
        let u = |o: usize| u64::from_le_bytes(ix.data[o..o + 8].try_into().unwrap());
        out.push(DirectSell { mint, seller, tokens: u(8), min_sol: u(16) });
    }
    out
}

/// SOL out (lamports, before pump's fee) of selling `tokens` on a constant-product curve with virtual reserves (vsol, vtok),
/// as the replay prices the dump: vsol - vsol*vtok/(vtok+tokens)
pub fn sell_sol_out(vsol: u64, vtok: u64, tokens: u64) -> u64 {
    let (v, t, q) = (vsol as u128, vtok as u128, tokens as u128);
    if t + q == 0 { return 0; }
    (v - v * t / (t + q)) as u64
}

/// the pump TradeEvent (Anchor event `bddb7fd34ee661ee`) fields the dip features need; `fbps` / `cbps`: pump's protocol and
/// creator fee bps at offsets 161 / 209 (the collector's a_extract; 0 when the event is shorter)
#[derive(Clone, Debug, PartialEq)]
pub struct TradeEvent { pub mint: Pk, pub sol: u64, pub tok: u64, pub buy: bool, pub user: Pk, pub vsol: u64, pub vtok: u64, pub fbps: u64, pub cbps: u64 }

pub const TRADE_EVENT_DISC: [u8; 8] = [189, 219, 127, 211, 78, 230, 97, 238];

fn trade_event(raw: &[u8]) -> Option<TradeEvent> {
    if raw.len() < 113 || raw[..8] != TRADE_EVENT_DISC { return None; }
    let u = |o: usize| u64::from_le_bytes(raw[o..o + 8].try_into().unwrap());
    let pk = |o: usize| -> Pk { raw[o..o + 32].try_into().unwrap() };
    let (fbps, cbps) = if raw.len() >= 217 { (u(161), u(209)) } else { (0, 0) };
    Some(TradeEvent { mint: pk(8), sol: u(40), tok: u(48), buy: raw[56] == 1, user: pk(57), vsol: u(97), vtok: u(105), fbps, cbps })
}

/// pump's CreateEvent (Anchor `sha256("event:CreateEvent")[..8]`): name, symbol, uri (u32-prefixed strings), then mint,
/// bonding curve, user, creator (the collector's parse_create)
#[derive(Clone, Debug, PartialEq)]
pub struct CreateEvent { pub mint: Pk, pub bonding_curve: Pk, pub user: Pk, pub creator: Pk }

pub const CREATE_EVENT_DISC: [u8; 8] = [27, 114, 169, 77, 222, 235, 99, 118];

fn create_event(raw: &[u8]) -> Option<CreateEvent> {
    if raw.len() < 8 || raw[..8] != CREATE_EVENT_DISC { return None; }
    let mut o = 8usize;
    for _ in 0..3 { let n = u32::from_le_bytes(raw.get(o..o + 4)?.try_into().ok()?) as usize; o += 4 + n; }
    let pk = |j: usize| -> Option<Pk> { raw.get(o + 32 * j..o + 32 * (j + 1)).and_then(|b| b.try_into().ok()) };
    Some(CreateEvent { mint: pk(0)?, bonding_curve: pk(1)?, user: pk(2)?, creator: pk(3)? })
}

/// pump CreateEvents from an executed tx's log lines ("Program data: <base64>")
pub fn create_events(logs: &[String]) -> Vec<CreateEvent> {
    use base64::Engine as _;
    let mut out = Vec::new();
    for l in logs {
        let Some(rest) = l.strip_prefix("Program data: ") else { continue };
        for part in rest.split_whitespace() {
            if let Ok(b) = base64::engine::general_purpose::STANDARD.decode(part) { if let Some(e) = create_event(&b) { out.push(e); } }
        }
    }
    out
}

/// a launch is "mayhem" when its create tx ran pump's InitializeMayhemState (the collector's `ixn` log names)
pub fn logs_have_mayhem(logs: &[String]) -> bool { logs.iter().any(|l| l == "Program log: Instruction: InitializeMayhemState") }

/// pump TradeEvents from an executed tx's log lines ("Program data: <base64>"), in log order (the collector's decode).
/// Logs can be truncated on busy txs; the same events then still sit in pump's self-CPI inner instructions (see
/// `trade_events_from_inner`), which an executed feed must also read.
pub fn trade_events(logs: &[String]) -> Vec<TradeEvent> {
    use base64::Engine as _;
    let mut out = Vec::new();
    for l in logs {
        let Some(rest) = l.strip_prefix("Program data: ") else { continue };
        for part in rest.split_whitespace() {
            if let Ok(b) = base64::engine::general_purpose::STANDARD.decode(part) { if let Some(e) = trade_event(&b) { out.push(e); } }
        }
    }
    out
}

/// the same events from pump's self-CPI event instructions (inner instruction data = 8-byte Anchor event-CPI tag, then the
/// event bytes)
pub fn trade_events_from_inner(inner_data: &[Vec<u8>]) -> Vec<TradeEvent> {
    inner_data.iter().filter_map(|d| if d.len() > 8 { trade_event(&d[8..]) } else { None }).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    fn load_json(p: &str) -> Option<Value> { std::fs::read_to_string(p).ok().and_then(|s| serde_json::from_str(&s).ok()) }

    #[test]
    fn dip_parity_with_python() {
        let root = env!("CARGO_MANIFEST_DIR");
        let (Some(par), Some(mj)) = (load_json(&format!("{root}/testdata/dip_parity.json")), load_json(&format!("{root}/testdata/frozen_dip4_L35.json"))) else {
            eprintln!("dip parity data missing: skipped"); return;
        };
        let g = Gbdt::from_json(&mj).expect("model");
        assert_eq!(g.features, FEATURES.iter().map(|s| s.to_string()).collect::<Vec<_>>(), "feature order");
        let tags = Tags { sn8: mj["sn8"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect(),
                          pro6: mj["pro6"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect() };
        let (mut n, mut feat_bad, mut score_bad, mut worst) = (0usize, 0usize, 0usize, 0f64);
        for l in par["launches"].as_array().unwrap() {
            let tr: Vec<Trade> = l["trades"].as_array().unwrap().iter().map(|r| {
                let a = r.as_array().unwrap();
                Trade { s: a[0].as_u64().unwrap(), i: a[1].as_u64().unwrap() as u32, user: a[2].as_str().unwrap().to_string(), buy: a[3].as_u64().unwrap() == 1,
                        sol: a[4].as_u64().unwrap(), tok: a[5].as_u64().unwrap(), vsol: a[6].as_u64().unwrap(), vtok: a[7].as_u64().unwrap(), syn: a[8].as_u64().unwrap() == 1 }
            }).collect();
            let la = Launch { slot: l["slot"].as_u64().unwrap(), g_end: l["g_end"].as_u64().unwrap() as usize,
                              insiders: l["insiders"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect(), glued: l["glued"].as_u64().unwrap() as usize };
            for e in l["events"].as_array().unwrap() {
                let k = e["k"].as_u64().unwrap() as usize;
                let f = features(&tr, k, &la, &tags);
                let py: Vec<f64> = e["feats"].as_array().unwrap().iter().map(|x| x.as_f64().unwrap()).collect();
                n += 1;
                let mismatch: Vec<(usize, f64, f64)> = f.iter().zip(py.iter()).enumerate().filter(|(_, (a, b))| (*a - *b).abs() > 1e-9 * (1.0 + b.abs())).map(|(j, (a, b))| (j, *a, *b)).collect();
                if !mismatch.is_empty() { feat_bad += 1; if feat_bad <= 5 { eprintln!("feature mismatch {} k={k}: {:?}", l["mint"], mismatch.iter().map(|(j, a, b)| (FEATURES[*j], *a, *b)).collect::<Vec<_>>()); } }
                let d = (g.score(&f) - e["score"].as_f64().unwrap()).abs(); worst = worst.max(d);
                if d > 1e-9 { score_bad += 1; }
            }
        }
        eprintln!("dip parity: {n} events, feature mismatches {feat_bad}, score mismatches {score_bad}, worst score diff {worst:e}");
        assert!(n > 100, "too few parity events");
        assert!(feat_bad * 100 <= n, "more than 1% of events have a feature mismatch");
        assert!(score_bad * 100 <= n, "more than 1% of events have a score mismatch");
    }

    // Real dip-trigger txs (legacy, v0 and v1; lookup tables; one tx with 12 sells and truncated logs), fetched read-only by
    // ops/overnight/dipshadow/make_sell_fixtures.py: wire bytes decoded with the shred feed's own parser, expected values
    // from the txs' own instructions and TradeEvents.
    #[test]
    fn direct_sells_and_trade_events_on_real_txs() {
        use base64::Engine as _;
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(fx) = load_json(&format!("{root}/testdata/dip_sells.json")) else { eprintln!("dip_sells.json missing: skipped"); return; };
        let b58 = crate::tx::b58;
        let (mut n_tx, mut n_sells, mut n_events) = (0, 0, 0);
        for f in fx.as_array().unwrap() {
            let wire = base64::engine::general_purpose::STANDARD.decode(f["wire_b64"].as_str().unwrap()).unwrap();
            let (mut tx, _) = crate::tx::parse_wire(&wire).expect("parse_wire");
            let pks = |k: &str| -> Vec<Pk> { f["loaded"][k].as_array().map(|a| a.iter().map(|x| crate::tx::pk(x.as_str().unwrap())).collect()).unwrap_or_default() };
            let (w, r) = (pks("writable"), pks("readonly"));
            if !w.is_empty() || !r.is_empty() { tx.loaded = Some((w, r)); }
            let got: Vec<(String, String, u64, u64)> = direct_sells(&tx).iter().map(|s| (b58(&s.mint), b58(&s.seller), s.tokens, s.min_sol)).collect();
            let want: Vec<(String, String, u64, u64)> = f["expected_sells"].as_array().unwrap().iter()
                .map(|e| (e["mint"].as_str().unwrap().to_string(), e["seller"].as_str().unwrap().to_string(), e["tokens"].as_u64().unwrap(), e["min_sol"].as_u64().unwrap())).collect();
            assert_eq!(got, want, "direct sells of {}", f["sig"]);
            let logs: Vec<String> = f["logs"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
            let ev: Vec<(String, u64, u64, bool, String, u64, u64)> = trade_events(&logs).iter().map(|e| (b58(&e.mint), e.sol, e.tok, e.buy, b58(&e.user), e.vsol, e.vtok)).collect();
            let want_ev: Vec<(String, u64, u64, bool, String, u64, u64)> = f["expected_events"].as_array().unwrap().iter().map(|e| (
                e["mint"].as_str().unwrap().to_string(), e["sol"].as_u64().unwrap(), e["tok"].as_u64().unwrap(), e["buy"].as_bool().unwrap(),
                e["user"].as_str().unwrap().to_string(), e["vsol"].as_u64().unwrap(), e["vtok"].as_u64().unwrap())).collect();
            assert_eq!(ev, want_ev, "trade events of {}", f["sig"]);
            // the dump's SOL from the pre-trade curve equals the event (pump's own math) for single-sell txs
            if got.len() == 1 && ev.len() == 1 && !ev[0].3 {
                let (vsol_post, vtok_post) = (ev[0].5, ev[0].6);
                let (vsol_pre, vtok_pre) = (vsol_post + ev[0].1, vtok_post - ev[0].2);
                let est = sell_sol_out(vsol_pre, vtok_pre, got[0].2);
                assert!((est as i128 - ev[0].1 as i128).abs() <= 1, "sell_sol_out {est} vs event {} in {}", ev[0].1, f["sig"]);
            }
            n_tx += 1; n_sells += got.len(); n_events += ev.len();
        }
        eprintln!("dip decoders: {n_tx} real txs, {n_sells} direct sells, {n_events} trade events, all matching");
        assert!(n_tx >= 5);
    }
}
