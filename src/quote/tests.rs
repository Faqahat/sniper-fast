//! PLAN-ADDENDUM WP-16 tests on recorded mainnet states (I-11: only testdata/ is read). `testdata/venue-parity/`
//! holds the venue-harness fixture snapshots (22 pools: PumpSwap, Raydium CPMM and AMM v4, DLMM, DAMM v2, one slot each)
//! and 1,316 real swaps run on them by the dumped mainnet programs in LiteSVM (`program/venue-harness` `capture_post`:
//! output, debit and every word the swap changed in the pool's accounts), the oracle here:
//! - the engine's quotes (arbx-sizing through `quote::leg`) equal the real programs;
//! - the engine's maths before WP-16 (`venues::legacy`) against the same swaps: the deviations of
//!   program/arbx-sizing/DESIGN.md §2.7, asserted and counted (the differential test, and the accuracy change);
//! - the accuracy monitor's predictions against the real post-states, crate path and legacy path;
//! - every refusal state the crate defines is a skip with its reason;
//! - sizing on a recorded HOTBOT route (GLL3 ↔ 6D4E, gaps made as venue-harness `tests/route.rs` does).
use super::*;
use crate::accuracy::{self, Pred};
use crate::feeds::src as asrc;
use crate::venues::legacy;
use base64::Engine as _;
use rustc_hash::FxHashMap as HashMap;
use serde_json::Value;
use std::collections::BTreeMap;
use std::sync::{Arc, OnceLock};

const DIR: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/testdata/venue-parity");

/// one fixture: the pool's accounts (owner, data) at one slot, and that slot's Clock
struct Fx { venue: Venue, pool: Pk, slot: u64, unix: i64, accts: HashMap<Pk, (Pk, Vec<u8>)> }

fn pk58(s: &str) -> Pk { crate::tx::pk(s) }

fn fixtures() -> &'static HashMap<Pk, Fx> {
    static F: OnceLock<HashMap<Pk, Fx>> = OnceLock::new();
    F.get_or_init(|| {
        let mut out = HashMap::default();
        let mut files: Vec<_> = std::fs::read_dir(format!("{DIR}/pools")).unwrap().map(|e| e.unwrap().path()).collect();
        files.sort();
        for f in files {
            let v: Value = serde_json::from_str(&std::fs::read_to_string(&f).unwrap()).unwrap();
            let accts = v["accounts"].as_array().unwrap().iter().map(|a| {
                let data = base64::engine::general_purpose::STANDARD.decode(a["data"].as_str().unwrap()).unwrap();
                (pk58(a["pubkey"].as_str().unwrap()), (pk58(a["owner"].as_str().unwrap()), data))
            }).collect();
            let pool = pk58(v["pool"].as_str().unwrap());
            out.insert(pool, Fx { venue: Venue::parse(v["venue"].as_str().unwrap()).unwrap(), pool, slot: v["clock"]["slot"].as_u64().unwrap(),
                unix: v["clock"]["unix_timestamp"].as_i64().unwrap(), accts });
        }
        out
    })
}

fn swaps() -> &'static Vec<Value> {
    static S: OnceLock<Vec<Value>> = OnceLock::new();
    S.get_or_init(|| {
        let v: Value = serde_json::from_str(&std::fs::read_to_string(format!("{DIR}/real-swaps.json")).unwrap()).unwrap();
        v["swaps"].as_array().unwrap().clone()
    })
}

fn find(prefix: &str) -> &'static Fx { fixtures().values().find(|f| crate::tx::b58(&f.pool).starts_with(prefix)).unwrap() }

fn hex(s: &str) -> Vec<u8> { (0..s.len() / 2).map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap()).collect() }

/// the fixture's accounts as store versions, with byte patches applied ([key, offset, hex])
fn accounts(fx: &Fx, patches: &Value) -> HashMap<Pk, Acct> {
    let mut m: HashMap<Pk, Vec<u8>> = fx.accts.iter().map(|(k, (_, d))| (*k, d.clone())).collect();
    for p in patches.as_array().into_iter().flatten() {
        let (k, o, b) = (pk58(p[0].as_str().unwrap()), p[1].as_u64().unwrap() as usize, hex(p[2].as_str().unwrap()));
        m.get_mut(&k).unwrap()[o..o + b.len()].copy_from_slice(&b);
    }
    m.into_iter().map(|(k, d)| (k, Acct::rpc(Arc::from(d), fx.slot, 0, 0, asrc::RPC_BOOT))).collect()
}

/// a patch list in the capture's format
fn patch(k: &Pk, off: usize, b: &[u8]) -> Value { serde_json::json!([crate::tx::b58(k), off, b.iter().map(|x| format!("{x:02x}")).collect::<String>()]) }

/// the state a real swap left: `pre` with the words it changed
fn post_of(pre: &HashMap<Pk, Acct>, post: &Value) -> HashMap<Pk, Acct> {
    let mut m: HashMap<Pk, Acct> = pre.clone();
    for a in post.as_array().into_iter().flatten() {
        let k = pk58(a["key"].as_str().unwrap());
        let Some(words) = a["words"].as_array() else { continue };
        let mut d = m[&k].data.to_vec();
        for w in words {
            let (o, v) = (w[0].as_u64().unwrap() as usize, w[1].as_u64().unwrap());
            d[o..o + 8].copy_from_slice(&v.to_le_bytes());
        }
        let slot = m[&k].slot + 1;
        m.insert(k, Acct::rpc(Arc::from(d), slot, 0, 0, asrc::RPC_BOOT));
    }
    m
}

/// the engine's metadata for a fixture pool (`pools::meta_of`, then what `boot` adds: token programs, DAMM's and DLMM's flags)
fn meta(fx: &Fx) -> PoolMeta {
    let (owner, data) = &fx.accts[&fx.pool];
    assert_eq!(*owner, fx.venue.program());
    let mut m = crate::pools::meta_of(fx.venue, &fx.pool, data).unwrap();
    let prog = |k: &Pk| fx.accts.get(k).map_or(*crate::pda::TOKEN_PROGRAM, |a| a.0);
    m.t0_prog = prog(&m.t0);
    m.t1_prog = prog(&m.t1);
    match m.venue {
        Venue::DammV2 => m.flag = [m.t0, m.t1].iter().all(|k| fx.accts.get(k).map_or(true, |a| crate::pools::mint_refused(&a.1).is_none())),
        Venue::Dlmm => m.flag = fx.accts.contains_key(&m.extra[0]),
        _ => {}
    }
    m
}

/// a DLMM fixture's bin arrays (index, key)
fn bin_arrays(fx: &Fx) -> Vec<(i64, Pk)> {
    let mut v: Vec<(i64, Pk)> = fx.accts.iter().filter(|(_, (o, d))| *o == fx.venue.program() && d.len() == 10_136)
        .map(|(k, (_, d))| (i64::from_le_bytes(d[8..16].try_into().unwrap()), *k)).collect();
    v.sort();
    v
}

/// one real swap's context: its pool, the engine's metadata, the pre-state, the arrays the harness passed
struct Case { fx: &'static Fx, m: PoolMeta, pre: HashMap<Pk, Acct>, arrays: Vec<(i64, Pk)>, passed: Vec<i64>, zfo: bool, x: u64 }

fn case(s: &Value) -> Case {
    let fx = &fixtures()[&pk58(s["pool"].as_str().unwrap())];
    let passed = s["dlmm_arrays"].as_array().map(|a| a.iter().map(|i| i.as_i64().unwrap()).collect()).unwrap_or_default();
    Case { fx, m: meta(fx), pre: accounts(fx, &s["patches"]), arrays: bin_arrays(fx), passed, zfo: s["dir"] == "0->1", x: s["amount_in"].as_u64().unwrap() }
}

impl Case {
    /// the engine's leg for this swap: the third party's own swap (`Use::Third`) with exactly the bin arrays it passed
    fn leg(&self) -> Result<Leg<'_>, Why> { self.leg_as(Use::Third) }
    fn leg_as(&self, u: Use) -> Result<Leg<'_>, Why> {
        let get = |k: &Pk| self.pre.get(k);
        let usable = |i: i64| self.passed.is_empty() || self.passed.contains(&i);
        leg(&self.m, self.zfo, &Src { get: &get, arrays: &self.arrays, usable: &usable, clock: clock(self.fx.slot, self.fx.unix) }, u)
    }
    /// the legacy maths' output and its post-state prediction (`accuracy::predict` before WP-16), on the same state
    /// and arrays
    fn legacy_pred(&self, x: u64) -> Option<(u64, Pred)> {
        let get = |k: &Pk| self.pre.get(k).map(|a| &a.data[..]);
        let m = &self.m;
        match m.venue {
            Venue::Dlmm => {
                let arrays: HashMap<i64, &[u8]> = self.arrays.iter().filter(|(i, _)| self.passed.is_empty() || self.passed.contains(i))
                    .filter_map(|(i, k)| Some((*i, get(k)?))).collect();
                let v = legacy::dlmm::View { pair: get(&m.pool)?, arrays: &arrays, over: None };
                let q = legacy::dlmm::quote(&v, self.zfo, x, self.fx.unix, true).ok()?;
                Some((q.out, Pred::Dlmm { active: q.end_active, bins: q.changed.clone() }))
            }
            Venue::DammV2 => {
                let mut p = legacy::dammv2::decode(get(&m.pool)?)?;
                if m.flag { p.transfer_fee_known_zero = true; }
                let (out, after) = legacy::dammv2::quote_exact_in(&p, self.zfo, x, self.fx.slot, self.fx.unix)?;
                Some((out, Pred::Damm { sqrt_price: after.sqrt_price }))
            }
            _ => {
                let pump_cfg = get(&crate::pools::PUMP_FEE_CONFIG).and_then(legacy::cp::decode_pump_fee_cfg).map(Arc::new);
                let extra: Vec<&[u8]> = m.extra.iter().filter_map(|k| get(k)).collect();
                let a = legacy::cp::Accounts { pool: get(&m.pool)?, vault0: get(&m.vault0)?, vault1: get(&m.vault1)?, extra };
                let s = legacy::cp::snapshot(m, &a, self.fx.slot, self.fx.unix, pump_cfg.as_ref()).ok()?;
                let q = legacy::cp::quote(&s, self.zfo, x)?;
                Some((q.out, Pred::Cp { r0: q.r0, r1: q.r1 }))
            }
        }
    }
}

/// a label for tallies: the venue (DLMM: with the pool, its pairs differ in kind), and the mutation when it is not the
/// snapshot itself
fn label(s: &Value) -> String {
    let v = s["venue"].as_str().unwrap();
    let v = if v == "DLMM" { format!("DLMM {}", &s["pool"].as_str().unwrap()[..4]) } else { v.to_string() };
    if s["case"] == "snapshot" { v } else { format!("{v} [{}]", s["case"].as_str().unwrap()) }
}

#[test]
fn every_reason_has_its_counter() {
    for r in REASONS {
        assert_eq!((r.reject, r.trigger, r.probe, r.pred), (&*format!("reject_{}", r.reason), &*format!("trigger_{}", r.reason),
            &*format!("probe_{}", r.reason), &*format!("pred_{}", r.reason)));
        assert_eq!(REASONS.iter().filter(|x| x.reason == r.reason).count(), 1, "{} twice", r.reason);
    }
    // every Abort the crate defines has a reason in the table
    use sz::error::*;
    let all = [Abort::Unsupported, Abort::Layout, Abort::TransferFee, Abort::TransferHook, Abort::Math, Abort::ModelRefused]
        .into_iter()
        .chain([PumpWhy::Mayhem, PumpWhy::Cashback, PumpWhy::Disabled, PumpWhy::Virtual, PumpWhy::FeeTotal, PumpWhy::FeeConfig, PumpWhy::EmptyReserves,
            PumpWhy::HeldExceedsVault, PumpWhy::UnknownTail].map(Abort::Pump))
        .chain([CpmmWhy::SwapDisabled, CpmmWhy::NotOpen, CpmmWhy::OwedExceedsVault, CpmmWhy::CreatorFeeOn, CpmmWhy::Fee, CpmmWhy::EmptyReserves].map(Abort::Cpmm))
        .chain([AmmWhy::Status, AmmWhy::PnlExceedsVault, AmmWhy::Fee, AmmWhy::EmptyReserves].map(Abort::Amm))
        .chain([DlmmWhy::Status, DlmmWhy::NotActive, DlmmWhy::FunctionType, DlmmWhy::CollectFeeMode, DlmmWhy::ZeroPrice, DlmmWhy::ActivationType].map(Abort::Dlmm))
        .chain([DammWhy::Status, DammWhy::NotActive, DammWhy::RateLimiter, DammWhy::Mode, DammWhy::Fee100, DammWhy::Liquidity, DammWhy::Range, DammWhy::Time].map(Abort::Damm));
    for a in all { assert!(reason_row(abort_reason(a)).is_some(), "{a:?} -> {}", abort_reason(a)); assert!(Why::Abort(a).crate_reason().is_some()); }
    for w in [Why::PumpHeldCapacity, Why::Budget, Why::PumpQuoteNotSol, Why::AmmV4Token2022] { assert!(w.crate_reason().is_some(), "{w:?}"); }
    for w in [Why::Missing(Venue::Dlmm), Why::Unquotable(Venue::PumpSwap), Why::DlmmArray] { assert!(w.crate_reason().is_none(), "{w:?}"); }
}

/// The engine's quote (arbx-sizing through `quote::leg`) equals the real program on every recorded swap it does not
/// refuse: the same output and the same debit; a swap the program refuses is refused. Every refusal is checked against
/// the program too (WP-16 review F3): either the program fails the swap as well (the cashback coin 98ew: the engine's
/// leg cannot execute it), or the refusal is a Token-2022 transfer fee the program charges (Hmx1 CPMM 300 bps, 2cUM
/// DAMM v2 100 bps: `sz_transfer_fee`), where the crate's maths would be off by the fee
#[test]
fn the_engines_quotes_equal_the_real_programs() {
    let (mut exact, mut both_refuse, mut n_exact_out) = (0, 0, 0);
    let (mut refused_program_fails, mut refused_fee) = (BTreeMap::<String, usize>::new(), BTreeMap::<String, usize>::new());
    let mut problems = vec![];
    for s in swaps() {
        let c = case(s);
        let (ok, out, spent) = (s["ok"].as_bool().unwrap(), s["out"].as_u64().unwrap(), s["spent"].as_u64().unwrap());
        let pool4 = &s["pool"].as_str().unwrap()[..4];
        // an exact-out row (PumpSwap's `buy`, WP-16 review F6): `x` is the base out, quoted by the leg's exact-out quote
        let exact_out = s["exact_out"].as_bool().unwrap_or(false);
        let q = c.leg().and_then(|l| if exact_out { l.exact_out(c.x).expect("an exact-out row is a PumpSwap buy").map(|r| r.1) } else { l.quote(c.x) });
        if exact_out && q.is_ok() { n_exact_out += 1; }
        match q {
            Ok(q) if ok && q.out == out && q.spent == spent => exact += 1,
            Err(w) if w.whole_leg() || matches!(w, Why::Abort(_)) => {
                let key = format!("{pool4} {}", w.reason());
                if !ok || out == 0 { *refused_program_fails.entry(key).or_default() += 1; }
                else if w.reason() == "sz_transfer_fee" { *refused_fee.entry(key).or_default() += 1; }
                else { problems.push(format!("{} {} {} x={}: FALSE REFUSAL {} while the program pays {out}", label(s), s["pool"], s["dir"], c.x, w.reason())); }
            }
            Err(_) if !ok || out == 0 => both_refuse += 1,
            q => problems.push(format!("{} {} {} x={}: engine {q:?}, program ok {ok} out {out} spent {spent}", label(s), s["pool"], s["dir"], c.x)),
        }
    }
    eprintln!("engine quotes vs the real programs: {exact} exact ({n_exact_out} exact-out buys quoted), {both_refuse} refused by both; refusals the program \
        refuses too {refused_program_fails:?}, transfer-fee refusals {refused_fee:?}");
    assert!(problems.is_empty(), "{} mismatches:\n{}", problems.len(), problems[..problems.len().min(20)].join("\n"));
    assert!(exact > 2_200, "{exact}");
    assert!(n_exact_out > 300, "PumpSwap exact-out buys quoted: {n_exact_out}");
    assert!(refused_fee.keys().all(|k| k.starts_with("Hmx1") || k.starts_with("2cUM")), "{refused_fee:?}");
    assert!(refused_program_fails.keys().all(|k| k == "98ew sz_pump_cashback" || k.ends_with("sz_transfer_fee")), "{refused_program_fails:?}");
    assert!(refused_program_fails.contains_key("98ew sz_pump_cashback"), "the cashback coin's swaps are recorded, all failed");
}

/// The differential test (PLAN-ADDENDUM WP-16; DESIGN.md §6.2): the engine's maths before WP-16 (`venues::legacy`) and
/// the crate on the same recorded states, both against the real programs. The crate is exact wherever it quotes; the
/// legacy maths deviates only in the classes DESIGN.md §2.7 documents, each asserted with its sign and size:
/// - PumpSwap `buy_exact_quote_in` (1->0): the missing "−1" in the base output and the missing debit adjustment: the
///   legacy output is above the program's;
/// - Raydium CPMM with the creator fee on the input: two fee ceils instead of one: at most one unit of input, so the
///   output differs by at most one unit's worth;
/// - DLMM: limit-order layers ignored and the fee on the output (collect_fee_mode 1, X->Y) charged on the input;
/// - AMM v4, PumpSwap sell and DAMM v2: identical.
/// The counts are the accuracy change for the user's amounts, printed per venue and mutation
#[test]
fn legacy_maths_vs_the_crate_on_recorded_states() {
    #[derive(Default, Debug)]
    struct T { n: usize, crate_exact: usize, legacy_exact: usize, legacy_off: usize, legacy_high: usize, legacy_refused: usize, max_rel_ppm: f64 }
    let mut tally: BTreeMap<String, T> = BTreeMap::new();
    let mut problems = vec![];
    for s in swaps() {
        // exact-in quotes (an exact-out buy has no legacy counterpart but the monitor's solve: see the accuracy test)
        if !s["ok"].as_bool().unwrap() || s["out"] == 0 || s["exact_out"] == true { continue; }
        let c = case(s);
        let real = s["out"].as_u64().unwrap();
        let Ok(l) = c.leg() else { continue };
        let Ok(q) = l.quote(c.x) else { continue };
        let t = tally.entry(label(s)).or_default();
        t.n += 1;
        if q.out == real { t.crate_exact += 1; }
        match c.legacy_pred(c.x) {
            None => t.legacy_refused += 1,
            Some((o, _)) if o == real => t.legacy_exact += 1,
            Some((o, _)) => {
                t.legacy_off += 1;
                // above the program: an output the venue never pays (a phantom gap when it is the sell leg)
                if o > real { t.legacy_high += 1; }
                t.max_rel_ppm = t.max_rel_ppm.max((o as f64 - real as f64).abs() / real as f64 * 1e6);
                let pool = &c.pre[&c.fx.pool].data;
                let documented = match c.m.venue {
                    // §2.7 item 1: legacy over-estimates a buy's base output (eff instead of eff − 1; no overrun adjustment)
                    Venue::PumpSwap => !c.zfo && o > real,
                    // §2.7 item 3: creator fee on the input, two ceils: legacy's net input is at most one unit smaller
                    Venue::RayCpmm => {
                        let on = pool[389];
                        let on_input = pool[390] != 0 && (on == 0 || (on == 1 && c.zfo) || (on == 2 && !c.zfo));
                        let AnyLeg::Cpmm(cl) = l.any else { unreachable!() };
                        on_input && real > o && (real - o) as u128 <= cl.r_out as u128 / cl.r_in as u128 + 1
                    }
                    // §2.7 item 4: limit orders (function_type 2) and the fee on the output (collect_fee_mode 1)
                    Venue::Dlmm => pool[35] == 2 || pool[36] == 1,
                    Venue::RayAmmV4 | Venue::DammV2 => false,
                };
                if !documented { problems.push(format!("{} x={} {}: legacy {o} vs program {real} (crate {})", label(s), c.x, s["dir"], q.out)); }
            }
        }
    }
    eprintln!("{:<52} {:>5} {:>12} {:>13} {:>10} {:>12} {:>9} {:>12}", "venue [mutation]", "n", "crate exact", "legacy exact", "legacy off", "legacy above", "refused", "max off ppm");
    for (k, t) in &tally {
        eprintln!("{k:<52} {:>5} {:>12} {:>13} {:>10} {:>12} {:>9} {:>12.3}", t.n, t.crate_exact, t.legacy_exact, t.legacy_off, t.legacy_high, t.legacy_refused, t.max_rel_ppm);
    }
    assert!(problems.is_empty(), "{} undocumented deviations:\n{}", problems.len(), problems[..problems.len().min(20)].join("\n"));
    for (k, t) in &tally { assert_eq!(t.crate_exact, t.n, "{k}: the crate is exact on every swap it quotes"); }
    let sum = |f: &dyn Fn(&str) -> bool, g: fn(&T) -> usize| tally.iter().filter(|(k, _)| f(k)).map(|(_, t)| g(t)).sum::<usize>();
    assert!(sum(&|k| k.starts_with("PumpSwap"), |t| t.legacy_off) > 0, "PumpSwap buys deviate (§2.7 item 1)");
    assert!(sum(&|k| k.starts_with("DLMM"), |t| t.legacy_off) > 0, "DLMM deviates on limit-order and fee-on-output pairs (§2.7 item 4)");
    assert_eq!(sum(&|k| k.starts_with("RayAMMv4") || k.starts_with("DAMMv2"), |t| t.legacy_off), 0, "AMM v4 and DAMM v2 identical");
}

/// The accuracy monitor (`accuracy::predict`, now on arbx-sizing's amounts plus each venue's bookkeeping) against
/// what the real programs left in the pools: every prediction it makes is exact, and it predicts every recorded swap
/// but the ones the crate refuses for a reason the program confirms: the Token-2022 transfer-fee pools (Hmx1, 2cUM).
/// The counts are asserted per venue (WP-16 review F4: a monitor that stopped predicting a venue must fail here). The
/// same swaps through the legacy path (the monitor before WP-16) are counted beside it: the accuracy change, per venue
#[test]
fn accuracy_predictions_match_the_real_post_states() {
    #[derive(Default, Debug)]
    struct T { n: usize, exact: usize, unpredicted: usize, legacy_exact: usize, legacy_unpredicted: usize }
    let mut tally: BTreeMap<String, T> = BTreeMap::new();
    let mut unpredicted: BTreeMap<String, usize> = BTreeMap::new();
    let mut problems = vec![];
    for s in swaps() {
        if !s["ok"].as_bool().unwrap() { continue; }
        let c = case(s);
        let post = post_of(&c.pre, &s["post"]);
        let (getpre, getpost) = (|k: &Pk| c.pre.get(k), |k: &Pk| post.get(k));
        // the monitor holds the arrays the swap passed
        let arrays: Vec<(i64, Pk)> = c.arrays.iter().filter(|(i, _)| c.passed.contains(i)).copied().collect();
        let vpre = accuracy::View { get: &getpre, arrays: &arrays, now_unix: c.fx.unix, slot: c.fx.slot };
        let vpost = accuracy::View { get: &getpost, arrays: &arrays, now_unix: c.fx.unix, slot: c.fx.slot };
        let exact_out = s["exact_out"].as_bool().unwrap_or(false);
        let t = tally.entry(if exact_out { format!("{} exact-out", label(s)) } else { label(s) }).or_default();
        t.n += 1;
        match accuracy::predict(&c.m, &vpre, c.zfo, c.x, exact_out) {
            Ok((p, _)) => {
                let a = accuracy::actual(&c.m, &vpost, &p).expect("the committed state reads");
                if accuracy::compare(&p, &a).0 { t.exact += 1; }
                else if problems.len() < 30 { problems.push(format!("{} {} x={}: predicted {p:?}, committed {a:?}", label(s), s["dir"], c.x)); }
            }
            Err(e) => {
                t.unpredicted += 1;
                *unpredicted.entry(format!("{} {e:?}", &s["pool"].as_str().unwrap()[..4])).or_default() += 1;
            }
        }
        // the monitor before WP-16 solved an exact-out swap as the smallest exact-in size reaching the amount
        let legacy_x = if exact_out { crate::venues::solve_exact_in(c.x, |x| c.legacy_pred(x).map(|p| p.0)) } else { Some(c.x) };
        match legacy_x.and_then(|x| c.legacy_pred(x)) {
            Some((_, p)) => if accuracy::actual(&c.m, &vpost, &p).is_some_and(|a| accuracy::compare(&p, &a).0) { t.legacy_exact += 1; },
            None => t.legacy_unpredicted += 1,
        }
    }
    eprintln!("{:<52} {:>5} {:>8} {:>12} {:>13} {:>19}", "venue [mutation]", "n", "exact", "unpredicted", "legacy exact", "legacy unpredicted");
    for (k, t) in &tally { eprintln!("{k:<52} {:>5} {:>8} {:>12} {:>13} {:>19}", t.n, t.exact, t.unpredicted, t.legacy_exact, t.legacy_unpredicted); }
    let by = |f: &dyn Fn(&str) -> bool| tally.iter().filter(|(k, _)| f(k)).fold((0, 0, 0, 0), |a, (_, t)| (a.0 + t.n, a.1 + t.exact, a.2 + t.legacy_exact, a.3 + t.unpredicted));
    let mut per_venue = BTreeMap::new();
    for v in ["PumpSwap", "RayCPMM", "RayAMMv4", "DLMM", "DAMMv2"] {
        let (n, e, l, u) = by(&|k| k.starts_with(v));
        eprintln!("{v:<10} predictions exact: crate {e}/{n} ({:.1}%), legacy {l}/{n} ({:.1}%); unpredicted {u}", 100.0 * e as f64 / n as f64, 100.0 * l as f64 / n as f64);
        per_venue.insert(v, (n, e, u));
    }
    eprintln!("unpredicted: {unpredicted:?}");
    assert!(problems.is_empty(), "{} inexact predictions:\n{}", problems.len(), problems.join("\n"));
    // the only swaps not predicted are the transfer-fee pools' (the crate refuses them; the program charges the fee)
    assert!(unpredicted.keys().all(|k| k == "Hmx1 Refused(\"sz_transfer_fee\")" || k == "2cUM Refused(\"sz_transfer_fee\")"), "{unpredicted:?}");
    let fee = |p: &str| unpredicted.iter().filter(|(k, _)| k.starts_with(p)).map(|(_, n)| *n).sum::<usize>();
    for (v, (n, e, u)) in &per_venue {
        let allowed = match *v { "RayCPMM" => fee("Hmx1"), "DAMMv2" => fee("2cUM"), _ => 0 };
        assert!(*n >= 160, "{v}: only {n} recorded swaps");
        assert_eq!((*e, *u), (n - allowed, allowed), "{v}: every recorded swap but the transfer-fee pools' is predicted exactly");
    }
    assert!(fee("Hmx1") > 0 && fee("2cUM") > 0, "the transfer-fee pools' swaps are recorded");
    // the exact-out buys (WP-16 review F6) among them, every one predicted exactly
    let (n_out, e_out, _, _) = by(&|k| k.contains("exact-out"));
    assert!(n_out > 300 && e_out == n_out, "exact-out buys: {e_out} of {n_out} exact");
}

/// WP-16 review F4: the state stream follows every account a quote reads, so no route is `account_missing` for want of
/// one. Over every fixture pool, both directions, as our route's leg and as a third party's swap, `quote::leg` runs on a
/// store that holds only what the registry has the stream follow (`Registry::static_accounts`, plus the DLMM bin
/// arrays the engine follows around the active bin): it reads nothing else and misses nothing (PumpSwap's GlobalConfig
/// and fee config, every Token-2022 mint it scans, the CPMM config, ...). Each of those accounts has its role
/// (`watch_roles`), and the readiness check covers it (`consistency_set` + `other_parts`)
#[test]
fn the_stream_follows_every_account_a_quote_reads() {
    use std::cell::RefCell;
    let fxs: Vec<&Fx> = fixtures().values().collect();
    let metas: Vec<PoolMeta> = fxs.iter().map(|f| meta(f)).collect();
    let mut pairs: HashMap<(Pk, Pk), Vec<usize>> = HashMap::default();
    for (i, m) in metas.iter().enumerate() { pairs.entry(crate::pools::pair_key(&m.t0, &m.t1)).or_default().push(i); }
    let reg = crate::pools::Registry { pools: metas.clone(), by_pool: metas.iter().enumerate().map(|(i, m)| (m.pool, i)).collect(), pairs,
        seeds: Default::default(), ours: Default::default() };
    let followed: std::collections::HashSet<Pk> = reg.static_accounts().into_iter().collect();
    let roles: std::collections::HashSet<Pk> = reg.watch_roles().into_iter().map(|r| r.0).collect();
    assert_eq!(followed, roles, "every followed account has its role and nothing else");
    assert!(followed.contains(&*crate::pools::PUMP_GLOBAL_CONFIG) && followed.contains(&*crate::pools::PUMP_FEE_CONFIG));
    let (mut legs, mut t22) = (0, 0);
    for (fx, m) in fxs.iter().zip(&metas) {
        let pre = accounts(fx, &Value::Null);
        let arrays = bin_arrays(fx);
        let read: RefCell<Vec<Pk>> = RefCell::new(vec![]);
        let is_array = |k: &Pk| arrays.iter().any(|a| a.1 == *k);
        let get = |k: &Pk| { read.borrow_mut().push(*k); if followed.contains(k) || is_array(k) { pre.get(k) } else { None } };
        let parts: Vec<Pk> = crate::store::consistency_set(m).into_iter().chain(crate::store::other_parts(m)).collect();
        for zfo in [true, false] {
            for u in [Use::Route { dlmm_budget: DLMM_BUDGET_ALONE }, Use::Third] {
                read.borrow_mut().clear();
                let r = leg(m, zfo, &Src { get: &get, arrays: &arrays, usable: &|_| true, clock: clock(fx.slot, fx.unix) }, u);
                let pool = crate::tx::b58(&m.pool);
                assert!(!matches!(r, Err(Why::Missing(_))), "{pool} zfo {zfo} {u:?}: an account the quote reads is not followed: {:?}",
                    read.borrow().iter().filter(|k| !followed.contains(*k) && !is_array(k)).map(crate::tx::b58).collect::<Vec<_>>());
                for k in read.borrow().iter().filter(|k| !is_array(k)) {
                    assert!(followed.contains(k), "{pool}: the quote read {} the stream does not follow", crate::tx::b58(k));
                    assert!(parts.contains(k), "{pool}: the quote read {} the readiness check does not cover", crate::tx::b58(k));
                }
                legs += 1;
            }
        }
        if [m.t0_prog, m.t1_prog].contains(&*crate::pda::TOKEN_2022) { t22 += 1; }
    }
    assert!(legs >= 120 && t22 >= 10, "{legs} legs, {t22} pools with a Token-2022 mint");
}

/// a case on fixture `prefix` with `patches`, every fixture bin array followed and usable
fn case_on(prefix: &str, patches: Vec<Value>, zfo: bool, x: u64) -> Case {
    let fx = find(prefix);
    Case { fx, m: meta(fx), pre: accounts(fx, &Value::Array(patches)), arrays: bin_arrays(fx), passed: vec![], zfo, x }
}

fn reason_of(c: &Case, u: Use) -> &'static str {
    match c.leg_as(u) { Err(w) => w.reason(), Ok(l) => match l.quote(c.x) { Ok(_) => "ok", Err(w) => w.reason() } }
}

const ROUTE: Use = Use::Route { dlmm_budget: DLMM_BUDGET_ALONE };

/// PLAN-ADDENDUM WP-16: every refusal state arbx-sizing defines is a skip with its own reason (the route's
/// decisions.jsonl reason, counted `reject_<reason>`), on recorded mainnet pools with the state mutated as venue-harness
/// `tests/adversarial.rs` does: a DAMM v2 rate limiter in force (our leg only: a third party's swap is priced), the
/// PumpSwap held-back quote above the vault and a sell past what it leaves, a Token-2022 transfer fee and hook, a DLMM
/// walk past its CU budget or our bin-array window, and the venue states the crate does not model
#[test]
fn every_refusal_state_is_a_skip_with_its_reason() {
    let u64b = |v: u64| v.to_le_bytes().to_vec();
    // DAMM v2 rate limiter (mode 2) in force for B->A (2E8c: OnlyB, timestamp activation)
    let d = find("2E8c");
    let dp = &d.accts[&d.pool].1;
    assert_eq!(dp[484], 1, "2E8c collects fees in B only");
    let rb = u64::from_le_bytes(d.accts[&meta(d).vault1].1[64..72].try_into().unwrap());
    let mut bf = vec![0u8; 32];
    bf[0..8].copy_from_slice(&10_000_000u64.to_le_bytes());
    bf[8] = 2;
    bf[14..16].copy_from_slice(&50u16.to_le_bytes());
    bf[16..20].copy_from_slice(&3_600u32.to_le_bytes());
    bf[20..24].copy_from_slice(&4_000u32.to_le_bytes());
    bf[24..32].copy_from_slice(&(rb / 2_000).max(1).to_le_bytes());
    let limiter = || vec![patch(&d.pool, 8, &bf), patch(&d.pool, 472, &u64b((d.unix - 600) as u64))];
    assert_eq!(reason_of(&case_on("2E8c", limiter(), false, 1_000_000), ROUTE), "sz_damm_rate_limiter", "our leg cannot pass the sysvar (6049)");
    assert_eq!(reason_of(&case_on("2E8c", limiter(), false, 1_000_000), Use::Third), "ok", "a third party's swap is priced with the limiter's fee");
    assert_eq!(reason_of(&case_on("2E8c", limiter(), true, 1_000_000), ROUTE), "ok", "A->B is not limited");
    // PumpSwap: the held-back quote (u64 @271, @279) above the vault refuses both directions; below it, a sell past
    // Q − held is a capacity skip (6063 on chain) and the largest one that fits quotes
    let p = find("CyJw");
    let pm = meta(p);
    let q = u64::from_le_bytes(p.accts[&pm.vault1].1[64..72].try_into().unwrap());
    for zfo in [true, false] {
        assert_eq!(reason_of(&case_on("CyJw", vec![patch(&p.pool, 271, &u64b(q + 1))], zfo, 1_000_000), ROUTE), "sz_pump_held_exceeds_vault");
    }
    let c = case_on("CyJw", vec![], true, 0);
    let l = c.leg_as(ROUTE).unwrap();
    let cap = l.any.cap_in().unwrap();
    assert!(l.quote(cap).is_ok());
    assert_eq!(l.quote(cap + 1).unwrap_err().reason(), "sz_pump_held_capacity");
    // Token-2022 transfer fee: Hmx1 (CPMM, 300 bps) and 2cUM (DAMM v2, 100 bps), whoever swaps
    for (pool, u) in [("Hmx1", ROUTE), ("Hmx1", Use::Third), ("2cUM", ROUTE), ("2cUM", Use::Third)] {
        assert_eq!(reason_of(&case_on(pool, vec![], true, 1_000), u), "sz_transfer_fee", "{pool}");
    }
    // a transfer hook with a program set: HOTBOT's mint (Token-2022) with its first extension turned into a hook
    let h = find("6D4E");
    let hm = meta(h);
    assert_eq!(hm.t0_prog, *crate::pda::TOKEN_2022);
    let mint = &h.accts[&hm.t0].1;
    assert_eq!((u16::from_le_bytes([mint[166], mint[167]]), u16::from_le_bytes([mint[168], mint[169]])), (18, 64), "MetadataPointer first");
    assert_eq!(reason_of(&case_on("6D4E", vec![patch(&hm.t0, 166, &14u16.to_le_bytes())], true, 1_000_000), ROUTE), "sz_transfer_hook");
    // DLMM: past the CU budget (bins read) and past the arrays our route names
    let big = 2_000_000_000_000u64;
    assert_eq!(reason_of(&case_on("6D4E", vec![], false, big), Use::Route { dlmm_budget: 3 }), "sz_budget");
    let mut c = case_on("6D4E", vec![], false, big);
    let active = i32::from_le_bytes(c.pre[&c.fx.pool].data[76..80].try_into().unwrap());
    let a0 = crate::venues::dlmm::array_index(active);
    c.passed = vec![a0];
    assert_eq!(reason_of(&c, ROUTE), "unquotable_dlmm_array", "liquidity lies beyond the one array we name");
    c.passed = vec![a0 + 1];
    assert_eq!(reason_of(&c, ROUTE), "unquotable_dlmm_array", "the active bin's array is not held");
    // venue states arbx-sizing does not model, and the routes we do not trade
    let gc = crate::pools::PUMP_GLOBAL_CONFIG.to_owned();
    for (pool, patches, zfo, want) in [
        ("GLL3", vec![patch(&find("GLL3").pool, 244, &[1])], false, "sz_pump_cashback"),
        // byte 270 is `is_holder_reward` (WP-16 review F2): priced; a byte that is no Borsh bool fails the program
        ("GLL3", vec![patch(&find("GLL3").pool, 270, &[1])], true, "ok"),
        ("GLL3", vec![patch(&find("GLL3").pool, 270, &[2])], true, "sz_layout"),
        ("GLL3", vec![patch(&find("GLL3").pool, 287, &[1])], true, "sz_pump_unknown_tail"),
        // a mayhem pool is priced on the fixed 1e15 supply (pinned on the dumped binary)
        ("GLL3", vec![patch(&find("GLL3").pool, 243, &[1])], true, "ok"),
        ("GLL3", vec![patch(&gc, 56, &[1 << 3])], false, "sz_pump_disabled"),
        ("GLL3", vec![patch(&gc, 56, &[1 << 3])], true, "ok"),
        ("6ejg", vec![], true, "pump_quote_not_sol"),
        ("GfAp", vec![patch(&find("GfAp").pool, 373, &u64b(find("GfAp").unix as u64 + 1_000))], true, "sz_cpmm_not_open"),
        ("GfAp", vec![patch(&find("GfAp").pool, 329, &[1 << 2])], true, "sz_cpmm_swap_disabled"),
        ("GfAp", vec![patch(&find("GfAp").pool, 389, &[3, 1])], true, "sz_cpmm_creator_fee_on"),
        ("3kQo", vec![patch(&find("3kQo").pool, 0, &u64b(0))], true, "sz_ammv4_status"),
        ("6D4E", vec![patch(&find("6D4E").pool, 82, &[1])], true, "sz_dlmm_status"),
        ("6D4E", vec![patch(&find("6D4E").pool, 35, &[3])], true, "sz_dlmm_function_type"),
        ("C8jd", vec![patch(&find("C8jd").pool, 481, &[1])], true, "sz_damm_status"),
    ] {
        assert_eq!(reason_of(&case_on(pool, patches, zfo, 1_000_000), ROUTE), want, "{pool} {want}");
    }
    assert_eq!(reason_of(&case_on("6ejg", vec![], true, 1_000_000), Use::Third), "ok", "a third party's swap on an exotic-quote pool is priced");
    // the census's classes on real pools (WP-16 review F1, F2): 300-byte pools, holder-reward pools (301 and 300 bytes),
    // a mayhem pool (priced on the fixed 1e15 supply), a cashback coin (refused: the engine's leg cannot execute it), a
    // 287-byte dust pool (non-SOL quote: priced for a third party's swap, not traded)
    for pool in ["9qKx", "FKfR", "EBNU", "5PGh", "3KFC", "8ewu", "GxqG"] {
        for zfo in [true, false] { assert_eq!(reason_of(&case_on(pool, vec![], zfo, 1_000_000), ROUTE), "ok", "{pool} zfo {zfo}"); }
    }
    assert_eq!(find("9qKx").accts[&find("9qKx").pool].1.len(), 300, "9qKx is a 300-byte pool");
    assert_eq!(reason_of(&case_on("98ew", vec![], true, 1_000_000), ROUTE), "sz_pump_cashback");
    assert_eq!(reason_of(&case_on("DDGN", vec![], true, 1_000), ROUTE), "pump_quote_not_sol");
    assert_eq!(reason_of(&case_on("DDGN", vec![], true, 1_000), Use::Third), "ok", "a 287-byte pool");
    // the pool lengths the program reads (211..=301 bytes, each missing trailing group read as zero); shorter or longer
    // is `sz_layout` (a longer pool is an unknown layout)
    for (len, want) in [(210usize, "sz_layout"), (211, "ok"), (243, "ok"), (270, "ok"), (287, "ok"), (300, "ok"), (302, "sz_layout")] {
        let mut c = case_on("GLL3", vec![], true, 1_000_000);
        let mut d = c.pre[&c.fx.pool].data.to_vec();
        d.resize(len, 0);
        c.pre.insert(c.fx.pool, Acct::rpc(Arc::from(d), c.fx.slot, 0, 0, asrc::RPC_BOOT));
        assert_eq!(reason_of(&c, ROUTE), want, "a {len}-byte pool");
    }
    // AMM v4 with a Token-2022 side: its v2 swap takes SPL Token only
    let mut c = case_on("3kQo", vec![], true, 1_000_000);
    c.m.t0_prog = *crate::pda::TOKEN_2022;
    assert_eq!(reason_of(&c, ROUTE), "sz_ammv4_token_2022");
}

/// the engine's sizing before WP-16 (`engine.rs::price_route` at master 323e3bf): the ladder, then a ternary refinement
/// between the best rung's neighbours, on the legacy maths
fn legacy_size(run: &dyn Fn(u64) -> Option<i64>, sizes: &[u64]) -> Option<(u64, i64)> {
    let mut top: Option<(u64, i64)> = None;
    let mut idx = 0;
    for (k, &x) in sizes.iter().enumerate() {
        if let Some(p) = run(x) { if top.map_or(true, |t| p > t.1) { top = Some((x, p)); idx = k; } }
    }
    let mut t = top?;
    if t.1 > 0 {
        let mut lo = if idx > 0 { sizes[idx - 1] } else { sizes[0] / 4 };
        let mut hi = sizes.get(idx + 1).copied().unwrap_or(sizes[idx]);
        for _ in 0..24 {
            if hi - lo < 1_000 { break; }
            let (m1, m2) = (lo + (hi - lo) / 3, hi - (hi - lo) / 3);
            if run(m1).unwrap_or(i64::MIN) < run(m2).unwrap_or(i64::MIN) { lo = m1; } else { hi = m2; }
        }
        let x = (lo + hi) / 2;
        if let Some(p) = run(x) { if p > t.1 { t = (x, p); } }
    }
    Some(t)
}

/// Sizing on a recorded route (PLAN-ADDENDUM WP-16 "route ... sizing through it"): HOTBOT GLL3 (PumpSwap) ↔ 6D4E (DLMM,
/// limit orders), GLL3's quote vault scaled to open a gap either way (venue-harness `tests/route.rs`), the Stage-0
/// ladder (top rung 4.2 SOL: the size cap). The crate's sizing (`quote::best`) is exact (predicted = realized, the
/// crate being the venue) and, where the route makes money, at the brute-force best size within the cap; the engine's
/// sizing before WP-16 is shown beside it with what it predicted and what its size really makes. The size never passes
/// the cap
#[test]
fn sizing_on_a_recorded_route() {
    let ladder: Vec<u64> = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 4.2].iter().map(|s| (s * 1e9) as u64).collect();
    let (top, lo) = (*ladder.last().unwrap(), ladder[0] / 4);
    let g = find("GLL3");
    let q = u64::from_le_bytes(g.accts[&meta(g).vault1].1[64..72].try_into().unwrap());
    eprintln!("{:<26} {:>14} {:>14} {:>14} | {:>14} {:>14} | {:>14} {:>14}", "route", "legacy size", "legacy pred", "legacy real", "crate size", "crate profit",
        "grid best x", "grid best");
    for num in [880u64, 940, 970, 995, 1_005, 1_030, 1_060, 1_120] {
        let gp = vec![patch(&meta(g).vault1, 64, &(q / 1_000 * num).to_le_bytes())];
        // GLL3 cheap (num < 1000): buy HOTBOT on GLL3 (quote in: 1->0), sell on 6D4E (X in: 0->1); else the reverse
        let (b, s) = if num < 1_000 { (case_on("GLL3", gp, false, 0), case_on("6D4E", vec![], true, 0)) } else { (case_on("6D4E", vec![], false, 0), case_on("GLL3", gp, true, 0)) };
        let u = Use::Route { dlmm_budget: DLMM_BUDGET_ALONE };
        let (lb, ls) = (b.leg_as(u).unwrap(), s.leg_as(u).unwrap());
        let exact = |x: u64| round_trip(&lb, &ls, x).ok().map(|t| t.profit());
        let new = best(&lb, &ls, &ladder, lo, top);
        // the legacy path: its own maths for the size and the prediction; the crate for what that size makes
        let legacy_run = |x: u64| -> Option<i64> {
            let (mid, _) = b.legacy_pred(x)?;
            let mut s2 = Case { fx: s.fx, m: s.m.clone(), pre: s.pre.clone(), arrays: s.arrays.clone(), passed: s.passed.clone(), zfo: s.zfo, x: mid };
            s2.x = mid;
            Some(s2.legacy_pred(mid)?.0 as i64 - x as i64)
        };
        let old = legacy_size(&legacy_run, &ladder);
        // brute force: a log grid over [lo, top] and a fine grid around the crate's size
        let mut grid: Vec<u64> = (0..400).map(|i| (lo as f64 * (top as f64 / lo as f64).powf(i as f64 / 399.0)) as u64).collect();
        if let Ok(t) = &new { grid.extend((0..200).map(|i| ((t.x as f64 * (0.95 + 0.1 * i as f64 / 199.0)) as u64).clamp(lo, top))); }
        let gbest = grid.iter().filter_map(|&x| exact(x).map(|p| (x, p))).max_by_key(|r| r.1);
        let name = if num < 1_000 { format!("GLL3 x{num}/1000 -> 6D4E") } else { format!("6D4E -> GLL3 x{num}/1000") };
        let real_old = old.and_then(|o| exact(o.0));
        eprintln!("{name:<26} {:>14} {:>14} {:>14} | {:>14} {:>14} | {:>14} {:>14}", old.map_or(0, |o| o.0), old.map_or(0, |o| o.1), real_old.unwrap_or(0),
            new.as_ref().map_or(0, |t| t.x), new.as_ref().map_or(0, |t| t.profit()), gbest.map_or(0, |g| g.0), gbest.map_or(0, |g| g.1));
        let t = new.unwrap();
        assert!(t.x <= top, "never past the size cap");
        assert_eq!(exact(t.x), Some(t.profit()), "the crate's profit is the exact round trip");
        // where the route makes money: at the brute-force best (the locator lands within a few units of the true
        // optimum; a grid point may be the optimum itself). Where it does not, the best rung, as before (below
        // min_profit whatever the size)
        match gbest {
            Some((_, gp)) if gp > 0 => assert!(t.profit() >= gp - 10, "{name}: crate {} < grid best {gp}", t.profit()),
            _ => assert_eq!(Some(t.profit()), ladder.iter().filter_map(|&x| exact(x)).max(), "{name}: the best rung"),
        }
        // and never below what the legacy size really makes on the same state
        if let Some(r) = real_old { assert!(t.profit() >= r, "{name}: crate {} < legacy size's real {r}", t.profit()); }
    }
}

/// WP-16 review F7: `best` stops quoting the ladder at the first rung whose exact profit falls below the one before, on
/// the premise that a round trip's profit is concave in its size. On recorded routes (HOTBOT GLL3 ↔ 6D4E, PumpSwap ↔
/// DLMM with limit orders, at eight gaps; and every PumpSwap, CPMM and AMM v4 fixture against itself with its SOL vault
/// moved -2% .. +10%, both ways), the exact profits along the whole ladder never rise again once they fall (the premise),
/// and `best` is never below the whole ladder's best rung
#[test]
fn sizing_stops_at_the_first_falling_rung() {
    let ladder: Vec<u64> = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 4.2].iter().map(|s| (s * 1e9) as u64).collect();
    let (top, lo) = (*ladder.last().unwrap(), ladder[0] / 4);
    let u = Use::Route { dlmm_budget: DLMM_BUDGET_ALONE };
    let mut routes = 0;
    let mut check = |name: &str, b: &Leg, s: &Leg| {
        let profits: Vec<Option<i64>> = ladder.iter().map(|&x| round_trip(b, s, x).ok().map(|t| t.profit())).collect();
        let quoted: Vec<i64> = profits.iter().flatten().copied().collect();
        if let Some(k) = quoted.windows(2).position(|w| w[1] < w[0]) {
            assert!(quoted[k + 1..].windows(2).all(|w| w[1] <= w[0]), "{name}: the profit rises again after falling: {profits:?}");
        }
        let Some(max) = quoted.iter().copied().max() else { return };
        let t = best(b, s, &ladder, lo, top).unwrap_or_else(|w| panic!("{name}: {w:?} with rungs {profits:?}"));
        assert!(t.profit() >= max, "{name}: best {} below the ladder's best rung {max}: {profits:?}", t.profit());
        routes += 1;
    };
    let g = find("GLL3");
    let q = u64::from_le_bytes(g.accts[&meta(g).vault1].1[64..72].try_into().unwrap());
    for num in [880u64, 940, 970, 995, 1_005, 1_030, 1_060, 1_120] {
        let gp = vec![patch(&meta(g).vault1, 64, &(q / 1_000 * num).to_le_bytes())];
        let (b, s) = if num < 1_000 { (case_on("GLL3", gp, false, 0), case_on("6D4E", vec![], true, 0)) } else { (case_on("6D4E", vec![], false, 0), case_on("GLL3", gp, true, 0)) };
        check(&format!("GLL3 x{num}/1000 <-> 6D4E"), &b.leg_as(u).unwrap(), &s.leg_as(u).unwrap());
    }
    for fx in fixtures().values().filter(|f| matches!(f.venue, Venue::PumpSwap | Venue::RayCpmm | Venue::RayAmmV4)) {
        let m = meta(fx);
        let sol_is_t0 = m.t0 == *WSOL;
        if !sol_is_t0 && m.t1 != *WSOL { continue; }
        let v = if sol_is_t0 { m.vault0 } else { m.vault1 };
        let amt = u64::from_le_bytes(fx.accts[&v].1[64..72].try_into().unwrap());
        for permille in [980u64, 995, 1_000, 1_005, 1_020, 1_100] {
            let pre = |p: u64| case_on(&crate::tx::b58(&fx.pool)[..8], vec![patch(&v, 64, &(amt / 1_000 * p).to_le_bytes())], false, 0);
            // more SOL in `hi`: the token is dearer there. Buy it on `lo` (spend SOL) and sell it on `hi`, and the reverse
            let (lo_b, hi_s) = (Case { zfo: sol_is_t0, ..pre(1_000) }, Case { zfo: !sol_is_t0, ..pre(permille) });
            let (hi_b, lo_s) = (Case { zfo: sol_is_t0, ..pre(permille) }, Case { zfo: !sol_is_t0, ..pre(1_000) });
            let name = format!("{} x{permille}/1000", &crate::tx::b58(&fx.pool)[..4]);
            if let (Ok(b), Ok(s)) = (lo_b.leg_as(u), hi_s.leg_as(u)) { check(&name, &b, &s); }
            if let (Ok(b), Ok(s)) = (hi_b.leg_as(u), lo_s.leg_as(u)) { check(&format!("{name} reversed"), &b, &s); }
        }
    }
    assert!(routes >= 60, "{routes} routes");
}

/// The DLMM walk budgets are the transaction's CU limit (1.4M) under the engine's CU estimate ((29k + legs)·1.1,
/// `engine.rs::price_route`): a route at its budget still fits, one bin more on every DLMM leg does not (WP-06 may
/// change the CU table: this test then says the budgets must follow)
#[test]
fn the_dlmm_budgets_are_the_cu_limit() {
    let est = |legs: u64| ((29_000 + legs) as f64 * 1.10).ceil() as u64;
    let other = [Venue::PumpSwap, Venue::RayCpmm, Venue::RayAmmV4, Venue::DammV2].iter().map(|v| v.leg_cu(0)).max().unwrap();
    // bins read bound bins crossed from above, so the estimate at the budget is the worst case
    assert!(est(other + Venue::Dlmm.leg_cu(DLMM_BUDGET_ALONE as u32)) <= 1_400_000);
    assert!(est(2 * Venue::Dlmm.leg_cu(DLMM_BUDGET_SHARED as u32)) <= 1_400_000);
    assert!(est(other + Venue::Dlmm.leg_cu(DLMM_BUDGET_ALONE as u32 + 3)) > 1_400_000, "the alone budget is tight");
    assert!(est(2 * Venue::Dlmm.leg_cu(DLMM_BUDGET_SHARED as u32 + 6)) > 1_400_000, "the shared budget is tight");
}

/// WP-16 review F7: the cost of one leg on the recorded states, the crate path (`quote::leg`, then 14 quotes) against
/// the engine's maths before WP-16 (`venues::legacy`: the snapshot as master built it per route, then 14 quotes),
/// median over the fixture pools of each venue and both directions; and `quote::best` on two recorded AMM v4 legs (the
/// Stage-0 benchmark's venue), with and without a gap. Timing only (no assertion):
/// `cargo test --release --lib per_leg_cost -- --ignored --nocapture`
#[test]
#[ignore]
fn per_leg_cost() {
    use std::hint::black_box;
    const N: u32 = 4_000;
    let ns = |f: &mut dyn FnMut()| { for _ in 0..N / 10 { f(); } let t = std::time::Instant::now(); for _ in 0..N { f(); } t.elapsed().as_nanos() as f64 / N as f64 };
    let median = |mut v: Vec<f64>| { v.sort_by(|a, b| a.partial_cmp(b).unwrap()); if v.is_empty() { 0.0 } else { v[v.len() / 2] } };
    for venue in [Venue::PumpSwap, Venue::RayCpmm, Venue::RayAmmV4, Venue::Dlmm, Venue::DammV2] {
        let (mut parse, mut crate_leg, mut legacy_leg) = (vec![], vec![], vec![]);
        for fx in fixtures().values().filter(|f| f.venue == venue) {
            for zfo in [true, false] {
                let c = Case { fx, m: meta(fx), pre: accounts(fx, &Value::Null), arrays: bin_arrays(fx), passed: vec![], zfo, x: 0 };
                let u = Use::Route { dlmm_budget: DLMM_BUDGET_ALONE };
                if c.leg_as(u).is_err() { continue; }
                let reserve = { let v = if zfo { c.m.vault0 } else { c.m.vault1 }; c.pre.get(&v).and_then(|a| token_amount(a)).unwrap_or(1 << 40) };
                let sizes: Vec<u64> = (0..14).map(|i| ((reserve as f64 / 1e6).max(1_000.0) * 1.9f64.powi(i)) as u64).collect();
                // only legs both paths quote (the legacy maths refuses holder-reward and mayhem pools)
                if !sizes.iter().any(|&x| c.legacy_pred(x).is_some()) { continue; }
                // the legacy leg as master built it per route (the PumpSwap fee config decoded once, at its store update)
                let get = |k: &Pk| c.pre.get(k).map(|a| &a.data[..]);
                let m = &c.m;
                let pump_cfg = get(&crate::pools::PUMP_FEE_CONFIG).and_then(legacy::cp::decode_pump_fee_cfg).map(Arc::new);
                let mut legacy_run: Box<dyn FnMut()> = match venue {
                    Venue::Dlmm => Box::new(|| {
                        let arrays: HashMap<i64, &[u8]> = c.arrays.iter().filter_map(|(i, k)| Some((*i, get(k)?))).collect();
                        let v = legacy::dlmm::View { pair: get(&m.pool).unwrap(), arrays: &arrays, over: None };
                        for &x in &sizes { black_box(legacy::dlmm::quote(&v, zfo, black_box(x), c.fx.unix, false).ok().map(|q| q.out)); }
                    }),
                    Venue::DammV2 => Box::new(|| {
                        let mut p = legacy::dammv2::decode(get(&m.pool).unwrap()).unwrap();
                        p.transfer_fee_known_zero = m.flag;
                        for &x in &sizes { black_box(legacy::dammv2::quote_exact_in(&p, zfo, black_box(x), c.fx.slot, c.fx.unix).map(|q| q.0)); }
                    }),
                    _ => Box::new(|| {
                        let extra: Vec<&[u8]> = m.extra.iter().filter_map(|k| get(k)).collect();
                        let a = legacy::cp::Accounts { pool: get(&m.pool).unwrap(), vault0: get(&m.vault0).unwrap(), vault1: get(&m.vault1).unwrap(), extra };
                        let Ok(s) = legacy::cp::snapshot(m, &a, c.fx.slot, c.fx.unix, pump_cfg.as_ref()) else { return };
                        for &x in &sizes { black_box(legacy::cp::quote(&s, zfo, black_box(x)).map(|q| q.out)); }
                    }),
                };
                parse.push(ns(&mut || { black_box(c.leg_as(u).is_ok()); }));
                crate_leg.push(ns(&mut || {
                    let l = c.leg_as(u).unwrap();
                    for &x in &sizes { black_box(l.quote(black_box(x)).ok()); }
                }));
                legacy_leg.push(ns(&mut *legacy_run));
            }
        }
        eprintln!("{venue:?}: legs {} | crate: parse {:.0} ns, parse + 14 quotes {:.0} ns | legacy: snapshot + 14 quotes {:.0} ns", parse.len(),
            median(parse), median(crate_leg), median(legacy_leg));
    }
    // a whole route's sizing on two AMM v4 legs: 3kQo against a copy of itself whose SOL vault holds `gap` more
    let a = find("3kQo");
    let am = meta(a);
    let sol_is_t0 = am.t0 == *crate::venues::WSOL;
    let sol_vault = if sol_is_t0 { am.vault0 } else { am.vault1 };
    let ladder: Vec<u64> = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 4.2].iter().map(|s| (s * 1e9) as u64).collect();
    fn src<'m>(am: &PoolMeta, a: &Fx, m: &'m HashMap<Pk, Acct>, zfo: bool) -> Leg<'m> {
        let get = |k: &Pk| m.get(k);
        leg(am, zfo, &Src { get: &get, arrays: &[], usable: &|_| true, clock: clock(a.slot, a.unix) }, Use::Route { dlmm_budget: DLMM_BUDGET_ALONE }).unwrap()
    }
    for (name, permille) in [("no gap", 1_000u64), ("1% gap", 1_010)] {
        let lo = accounts(a, &Value::Null);
        let mut hi = accounts(a, &Value::Null);
        let v = token_amount(&hi[&sol_vault]).unwrap();
        let mut d = hi[&sol_vault].data.to_vec();
        d[64..72].copy_from_slice(&(v / 1_000 * permille).to_le_bytes());
        hi.insert(sol_vault, Acct::rpc(Arc::from(d), a.slot, 0, 0, asrc::RPC_BOOT));
        // more SOL in `hi`: the token is dearer there, so buy it on `lo` (spend SOL) and sell it on `hi`
        let (b, s) = (src(&am, a, &lo, sol_is_t0), src(&am, a, &hi, !sol_is_t0));
        let t = best(&b, &s, &ladder, ladder[0] / 4, *ladder.last().unwrap());
        let route = ns(&mut || { black_box(best(&b, &s, &ladder, ladder[0] / 4, *ladder.last().unwrap()).ok()); });
        let both = ns(&mut || {
            let (b, s) = (src(&am, a, &lo, sol_is_t0), src(&am, a, &hi, !sol_is_t0));
            black_box(best(&b, &s, &ladder, ladder[0] / 4, *ladder.last().unwrap()).ok());
        });
        eprintln!("AMM v4 route (3kQo, {name}): quote::best {route:.0} ns, with both legs parsed {both:.0} ns; best {:?}", t.map(|t| (t.x, t.profit())));
    }
}
