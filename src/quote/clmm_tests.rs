//! PLAN-ADDENDUM WP-21 tests on recorded mainnet states (I-11: only testdata/ is read). `testdata/venue-parity/pools-clmm`
//! holds the venue harness's Raydium CLMM and Orca Whirlpool snapshots (20 pools, one slot each: every account `swap_v2`
//! takes, the mints, the AmmConfig, the bitmap extension, the oracle, the tick arrays around the price, and the accounts
//! that do not exist, `absent`), and `real-swaps-clmm.json` 2,968 real swaps run on them by the deployed programs in
//! LiteSVM (`capture_post --clmm`: exact in and exact out both ways, the output, the debit, the tick arrays the leg passed
//! and every word the swap changed). The oracle here:
//! - the engine's quotes of these venues (arbx-sizing through `quote::leg`, the arrays as the engine follows them) equal
//!   the real programs; every refusal is one the program makes too (or a transfer fee it charges);
//! - the accuracy monitor's post-states (`accuracy::predict`) equal the real ones;
//! - a route's legs (`Use::Route`) quote as the builder names them, and the size search runs over them;
//! - no input panics the quote path (byte mutations, sizes, Orca's deployed U256 division).
use super::*;
use crate::accuracy::{self, Pred};
use crate::feeds::src as asrc;
use crate::venues::clmm;
use base64::Engine as _;
use rustc_hash::FxHashMap as HashMap;
use serde_json::Value;
use std::collections::BTreeMap;
use std::sync::{Arc, OnceLock};

const DIR: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/testdata/venue-parity");

/// one fixture: the pool's accounts (owner, data) at one slot, the accounts that do not exist, that slot's Clock
pub(crate) struct Fx { pub venue: Venue, pub pool: Pk, pub slot: u64, pub unix: i64, pub accts: HashMap<Pk, (Pk, Vec<u8>)>, pub absent: Vec<Pk> }

fn pk58(s: &str) -> Pk { crate::tx::pk(s) }

pub(crate) fn fixtures() -> &'static HashMap<Pk, Fx> {
    static F: OnceLock<HashMap<Pk, Fx>> = OnceLock::new();
    F.get_or_init(|| {
        let mut out = HashMap::default();
        let mut files: Vec<_> = std::fs::read_dir(format!("{DIR}/pools-clmm")).unwrap().map(|e| e.unwrap().path()).collect();
        files.sort();
        for f in files {
            let v: Value = serde_json::from_str(&std::fs::read_to_string(&f).unwrap()).unwrap();
            let accts = v["accounts"].as_array().unwrap().iter().map(|a| {
                let data = base64::engine::general_purpose::STANDARD.decode(a["data"].as_str().unwrap()).unwrap();
                (pk58(a["pubkey"].as_str().unwrap()), (pk58(a["owner"].as_str().unwrap()), data))
            }).collect();
            let absent = v["absent"].as_array().into_iter().flatten().map(|a| pk58(a.as_str().unwrap())).collect();
            let pool = pk58(v["pool"].as_str().unwrap());
            out.insert(pool, Fx { venue: Venue::parse(v["venue"].as_str().unwrap()).unwrap(), pool, slot: v["clock"]["slot"].as_u64().unwrap(),
                unix: v["clock"]["unix_timestamp"].as_i64().unwrap(), accts, absent });
        }
        out
    })
}

fn swaps() -> &'static Vec<Value> {
    static S: OnceLock<Vec<Value>> = OnceLock::new();
    S.get_or_init(|| {
        let v: Value = serde_json::from_str(&std::fs::read_to_string(format!("{DIR}/real-swaps-clmm.json")).unwrap()).unwrap();
        v["swaps"].as_array().unwrap().clone()
    })
}

pub(crate) fn find(prefix: &str) -> &'static Fx { fixtures().values().find(|f| crate::tx::b58(&f.pool).starts_with(prefix)).unwrap() }

fn hex(s: &str) -> Vec<u8> { (0..s.len() / 2).map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap()).collect() }

/// the engine's metadata for a fixture pool (`pools::meta_of`, then the token programs `boot` reads from the mints)
pub(crate) fn meta(fx: &Fx) -> PoolMeta {
    let (owner, data) = &fx.accts[&fx.pool];
    assert_eq!(*owner, fx.venue.program());
    let mut m = crate::pools::meta_of(fx.venue, &fx.pool, data).unwrap();
    let prog = |k: &Pk| fx.accts.get(k).map_or(*crate::pda::TOKEN_PROGRAM, |a| a.0);
    m.t0_prog = prog(&m.t0);
    m.t1_prog = prog(&m.t1);
    m
}

/// the fixture's accounts as store versions (patched: [key, offset, hex]), the accounts that do not exist held empty (as
/// the engine records a read that does not find them)
pub(crate) fn accounts(fx: &Fx, patches: &Value) -> HashMap<Pk, Acct> {
    let mut m: HashMap<Pk, Vec<u8>> = fx.accts.iter().map(|(k, (_, d))| (*k, d.clone())).collect();
    for p in patches.as_array().into_iter().flatten() {
        let (k, o, b) = (pk58(p[0].as_str().unwrap()), p[1].as_u64().unwrap() as usize, hex(p[2].as_str().unwrap()));
        m.get_mut(&k).unwrap()[o..o + b.len()].copy_from_slice(&b);
    }
    for k in &fx.absent { m.entry(*k).or_default(); }
    m.into_iter().map(|(k, d)| (k, Acct::rpc(Arc::from(d), fx.slot, 0, 0, asrc::RPC_BOOT))).collect()
}

/// the tick arrays the engine follows for the fixture's pool (`venues::clmm::follow_list` on its pool and extension),
/// with the fixture's other tick arrays of the pool (the snapshot holds more for Raydium: the walk may use any held one)
pub(crate) fn followed(fx: &Fx, m: &PoolMeta, accts: &HashMap<Pk, Acct>) -> Vec<(i64, Pk)> {
    let get = |k: &Pk| accts.get(k).map(|a| a.data.to_vec());
    let mut l = crate::pools::clmm_arrays(m, &get, &[]);
    if m.venue == Venue::RayClmm {
        for (k, (o, d)) in &fx.accts {
            if *o == m.venue.program() && d.len() == arbx_sizing::venue::raydium_clmm::ARRAY_LEN {
                let st = i32::from_le_bytes(d[40..44].try_into().unwrap()) as i64;
                if !l.iter().any(|x| x.0 == st) { l.push((st, *k)); }
            }
        }
        l.sort();
    }
    l
}

/// one real swap's context
struct Case { fx: &'static Fx, m: PoolMeta, pre: HashMap<Pk, Acct>, arrays: Vec<(i64, Pk)>, passed: Vec<i64>, zfo: bool, x: u64, exact_out: bool }

fn case(s: &Value) -> Case {
    let fx = &fixtures()[&pk58(s["pool"].as_str().unwrap())];
    let m = meta(fx);
    let pre = accounts(fx, &s["patches"]);
    let arrays = followed(fx, &m, &pre);
    let passed = s["tick_arrays"].as_array().map(|a| a.iter().map(|i| i.as_i64().unwrap()).collect()).unwrap_or_default();
    Case { fx, m, pre, arrays, passed, zfo: s["dir"] == "0->1", x: s["amount_in"].as_u64().unwrap(), exact_out: s["exact_out"].as_bool().unwrap() }
}

impl Case {
    /// the engine's leg for the third party's swap (`Use::Third`), Raydium with exactly the tick arrays the swap passed
    fn leg_as(&self, u: Use) -> Result<Leg<'_>, Why> {
        let get = |k: &Pk| self.pre.get(k);
        let ray = self.m.venue == Venue::RayClmm;
        let usable = |i: i64| !ray || self.passed.contains(&i);
        leg(&self.m, self.zfo, &Src { get: &get, arrays: &self.arrays, usable: &usable, clock: clock(self.fx.slot, self.fx.unix) }, u)
    }
    fn quote_as(&self, u: Use) -> Result<sz::Quote, Why> {
        let l = self.leg_as(u)?;
        if self.exact_out { l.exact_out(self.x).expect("a CLMM leg quotes exact out").map(|r| r.1) } else { l.quote(self.x) }
    }
    fn quote(&self) -> Result<sz::Quote, Why> { self.quote_as(Use::Third) }
}

fn label(s: &Value) -> String {
    let v = format!("{} {}", s["venue"].as_str().unwrap(), &s["pool"].as_str().unwrap()[..4]);
    if s["case"] == "snapshot" { v } else { format!("{v} [{}]", s["case"].as_str().unwrap()) }
}

/// The engine's quotes of Raydium CLMM and Orca Whirlpool (arbx-sizing through `quote::leg`, from the store's account
/// bytes, the tick arrays as the engine follows them) equal the deployed programs on every recorded swap, exact in and
/// exact out: the same output and the same debit; a swap the program refuses is refused. Every refusal of the engine's is
/// checked against the program: it refuses too, or it is a Token-2022 transfer fee it charges (ASk8, 3%:
/// `sz_transfer_fee`)
#[test]
fn clmm_quotes_equal_the_real_programs() {
    let (mut exact, mut exact_out, mut both_refuse, mut cu_limit) = (BTreeMap::<String, usize>::new(), 0, 0, 0);
    let mut refused: BTreeMap<String, usize> = BTreeMap::new();
    let mut problems = vec![];
    for s in swaps() {
        let c = case(s);
        let (ok, out, spent) = (s["ok"].as_bool().unwrap(), s["out"].as_u64().unwrap(), s["spent"].as_u64().unwrap());
        let cu_wall = s["err"].as_str().is_some_and(|e| e.contains("exceeded CUs"));
        match c.quote() {
            Ok(q) if ok && q.out == out && q.spent == spent => { *exact.entry(s["venue"].as_str().unwrap().to_string()).or_default() += 1; if c.exact_out { exact_out += 1; } }
            // the venue ran out of the 1.4M CU on a swap of 140+ steps: a third party's swap the crate prices (it has no CU
            // model), which our route's leg never takes: its walk budget (`clmm_budget`) stops it first (`sz_budget`)
            Ok(_) if cu_wall => {
                cu_limit += 1;
                let r = c.quote_as(Use::Route { dlmm_budget: DLMM_BUDGET_ALONE });
                assert_eq!(r, Err(Why::Budget), "{} x={}: a route's leg past the CU wall", label(s), c.x);
            }
            Err(_) if !ok || out == 0 => both_refuse += 1,
            Err(w) if w.reason() == "sz_transfer_fee" => *refused.entry(format!("{} {}", &s["pool"].as_str().unwrap()[..4], w.reason())).or_default() += 1,
            q => problems.push(format!("{} {} x={} exact_out={}: engine {q:?}, program ok {ok} out {out} spent {spent}", label(s), s["dir"], c.x, c.exact_out)),
        }
    }
    eprintln!("CLMM quotes vs the deployed programs: exact {exact:?} ({exact_out} exact out), {both_refuse} refused by both, {cu_limit} past the venue's CU \
        limit (a route's walk budget refuses them), transfer-fee refusals {refused:?}");
    assert!(problems.is_empty(), "{} mismatches:\n{}", problems.len(), problems[..problems.len().min(20)].join("\n"));
    assert!(exact.get("RayCLMM").copied().unwrap_or(0) > 1_500 && exact.get("Whirlpool").copied().unwrap_or(0) > 500, "{exact:?}");
    assert!(exact_out > 1_000, "{exact_out}");
    assert!(refused.keys().all(|k| k.starts_with("ASk8")), "{refused:?}");
}

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

/// The accuracy monitor on these venues (DESIGN.md §9.0 item 7): its prediction of the pool after a real swap (the
/// crate's `PostSwap`: sqrt price, tick, liquidity, the fee side's fee growth and fees owed, Raydium's dynamic-fee and
/// Orca's oracle variables) equals what the deployed program left, on every recorded swap it predicts; it predicts every
/// one but the transfer-fee pool's (ASk8)
#[test]
fn clmm_accuracy_predictions_match_the_real_post_states() {
    let (mut n, mut exact, mut fee) = (BTreeMap::<String, usize>::new(), BTreeMap::<String, usize>::new(), BTreeMap::<String, usize>::new());
    let mut unpredicted: BTreeMap<String, usize> = BTreeMap::new();
    let mut problems = vec![];
    for s in swaps() {
        if !s["ok"].as_bool().unwrap() { continue; }
        let c = case(s);
        let post = post_of(&c.pre, &s["post"]);
        let (getpre, getpost) = (|k: &Pk| c.pre.get(k), |k: &Pk| post.get(k));
        let vpre = accuracy::View { get: &getpre, arrays: &c.arrays, now_unix: c.fx.unix, slot: c.fx.slot };
        let vpost = accuracy::View { get: &getpost, arrays: &c.arrays, now_unix: c.fx.unix, slot: c.fx.slot };
        let v = s["venue"].as_str().unwrap().to_string();
        *n.entry(v.clone()).or_default() += 1;
        match accuracy::predict(&c.m, &vpre, c.zfo, c.x, c.exact_out) {
            Ok((p, _)) => {
                assert!(matches!(p, Pred::Clmm(_)), "{p:?}");
                let a = accuracy::actual(&c.m, &vpost, &p).expect("the committed state reads");
                if accuracy::compare(&p, &a).0 { *exact.entry(v).or_default() += 1; }
                else if problems.len() < 20 { problems.push(format!("{} {} x={} exact_out={}: predicted {p:?}, committed {a:?}", label(s), s["dir"], c.x, c.exact_out)); }
            }
            Err(e) => {
                *unpredicted.entry(format!("{} {e:?}", &s["pool"].as_str().unwrap()[..4])).or_default() += 1;
                if s["pool"].as_str().unwrap().starts_with("ASk8") { *fee.entry(v).or_default() += 1; }
            }
        }
    }
    eprintln!("CLMM accuracy: {n:?} swaps, {exact:?} exact; not predicted {unpredicted:?}");
    assert!(problems.is_empty(), "{} inexact:\n{}", problems.len(), problems.join("\n"));
    assert!(unpredicted.keys().all(|k| k.starts_with("ASk8")), "{unpredicted:?}");
    for (v, k) in &n { assert_eq!(exact.get(v).copied().unwrap_or(0) + fee.get(v).copied().unwrap_or(0), *k, "{v}: every swap predicted exactly but the fee pool's"); }
}

/// the crate's refusals carry their own reasons, each with its four counters (`every_reason_has_its_counter` for kinds
/// 7 and 8), and a refusal of the arrays we hold is ours (`unquotable_clmm_array`), not the pool's
#[test]
fn clmm_reasons_and_their_counters() {
    let clmm = [ClmmWhy::Status, ClmmWhy::NotOpen, ClmmWhy::Fee, ClmmWhy::BitmapExtension, ClmmWhy::NoLiquidity, ClmmWhy::TickArrays, ClmmWhy::PriceLimit,
        ClmmWhy::State, ClmmWhy::MintPaused, ClmmWhy::MintFrozen].map(Abort::Clmm);
    let whirl = [WhirlWhy::TradeNotEnabled, WhirlWhy::Timestamp, WhirlWhy::TickArrays, WhirlWhy::PriceLimit, WhirlWhy::State, WhirlWhy::MintPaused,
        WhirlWhy::MintFrozen].map(Abort::Whirl);
    for a in clmm.into_iter().chain(whirl) {
        let r = abort_reason(a);
        assert!(r.starts_with("sz_clmm_") || r.starts_with("sz_whirl_"), "{r}");
        let row = reason_row(r).unwrap_or_else(|| panic!("{r} has no counters"));
        assert_eq!((row.reject, row.pred), (&*format!("reject_{r}"), &*format!("pred_{r}")));
        assert!(Why::Abort(a).crate_reason().is_some() && Why::Abort(a).whole_leg());
    }
    for w in [Why::VenueUpgraded, Why::MintPaused, Why::MintFrozen] { assert!(w.crate_reason().is_some() && w.whole_leg(), "{w:?}"); }
    assert_eq!(clmm_abort(Abort::Clmm(ClmmWhy::TickArrays)), Why::ClmmArray);
    assert_eq!(clmm_abort(Abort::Whirl(WhirlWhy::TickArrays)), Why::ClmmArray);
    assert_eq!((Why::ClmmArray.reason(), Why::Missing(Venue::Whirlpool).reason(), Why::Unquotable(Venue::RayClmm).reason()),
        ("unquotable_clmm_array", "unquotable_clmm_array", "unquotable_clmm"));
    assert!(!Why::ClmmArray.whole_leg() && Why::ClmmArray.crate_reason().is_none());
    // the CU table's buckets and the fallback (DESIGN.md §9.0 item 6)
    assert_eq!(crate::cu_table::leg_key(Venue::RayClmm, 3), "RayClmm|2-3");
    assert_eq!(crate::cu_table::leg_key(Venue::Whirlpool, 1), "Whirlpool|1");
    assert_eq!((Venue::RayClmm.leg_cu(5), Venue::Whirlpool.leg_cu(0)), (114_000, 58_000));
    assert_eq!(clmm_budget(DLMM_BUDGET_ALONE), 100);
    assert_eq!(clmm_budget(DLMM_BUDGET_SHARED), 50);
}

/// Orca refuses a Clock before its own stamps (`Whirl(Timestamp)`): the engine quotes with the Clock of the slot it targets,
/// raised to the pool's and the oracle's stamps when the Clock sysvar's version lags the pool's write (DESIGN.md §9.0
/// item 4): an older Clock quotes as the stamps' own time, not a refusal
#[test]
fn whirlpool_quotes_never_before_its_stamps() {
    for prefix in ["4uny", "G1vH", "Czfq"] {
        let fx = find(prefix);
        let m = meta(fx);
        let accts = accounts(fx, &Value::Null);
        let arrays = followed(fx, &m, &accts);
        let get = |k: &Pk| accts.get(k);
        let q = |unix: i64| leg(&m, true, &Src { get: &get, arrays: &arrays, usable: &|_| true, clock: clock(fx.slot, unix) }, Use::Third).and_then(|l| l.quote(1_000_000));
        assert!(q(fx.unix).is_ok(), "{prefix}");
        // a Clock an hour older than the snapshot's: the pool's stamps are newer, the quote is priced at them, not refused
        let pool = &accts[&m.pool].data;
        let stamp = u64::from_le_bytes(pool[261..269].try_into().unwrap()) as i64;
        let early = q(fx.unix - 3_600).unwrap_or_else(|w| panic!("{prefix}: {w:?}"));
        assert_eq!(early, q(stamp).unwrap(), "{prefix}");
    }
}

/// A route's CLMM legs (`Use::Route`): the walk budget of the route's CU limit (`clmm_budget`), the size search over them
/// (`quote::best`: the ladder, then the crate's locator over the exact swap steps) and the tick arrays the builder names
/// (`Leg::clmm_arrays`: the walk's arrays in walk order, then one held buffer array, at most 7 with the extension);
/// Orca's legs name the program's own 3 (`whirl_leg_starts`), each held or known not to exist
#[test]
fn clmm_route_legs_quote_as_the_builder_names_them() {
    // the J6pQ/SOL pair on both venues (venue-harness tests/clmm_route.rs), and Orca's 2zMM/SOL with PumpSwap 9qKx
    let (ray, orca) = (find("DCALKkpd"), find("4uny6Y7d"));
    let (rm, om) = (meta(ray), meta(orca));
    let mut accts = accounts(ray, &Value::Null);
    accts.extend(accounts(orca, &Value::Null));
    let (ra, oa) = (followed(ray, &rm, &accts), followed(orca, &om, &accts));
    let get = |k: &Pk| accts.get(k);
    let unix = ray.unix.max(orca.unix);
    let all = |_: i64| true;
    let src = |arrays: &'static [(i64, Pk)]| Src { get: &get, arrays, usable: &all, clock: clock(ray.slot.max(orca.slot), unix) };
    let (ra, oa): (&'static [(i64, Pk)], &'static [(i64, Pk)]) = (Box::leak(ra.into_boxed_slice()), Box::leak(oa.into_boxed_slice()));
    let u = Use::Route { dlmm_budget: DLMM_BUDGET_SHARED };
    for zfo in [true, false] {
        let rl = leg(&rm, zfo, &src(ra), u).unwrap();
        let AnyLeg::RayClmm(c) = rl.any else { panic!() };
        assert_eq!(c.budget(), 50, "two walking legs share the CU limit");
        for x in [1_000_000u64, 50_000_000, 1_000_000_000] {
            let Ok(w) = rl.walk(x) else { continue };
            let names = rl.clmm_arrays(x).unwrap().unwrap();
            assert!(!names.is_empty() && names.len() + c.has_extension() as usize <= 7, "{names:?}");
            // every name is a held, initialized array, in walk order
            for st in &names { assert!(ra.iter().any(|(i, _)| *i == *st as i64), "{st}"); }
            let ord: Vec<i32> = names.clone();
            let mut sorted = ord.clone();
            sorted.sort_by_key(|s| if zfo { -(*s as i64) } else { *s as i64 });
            assert_eq!(ord, sorted, "walk order");
            assert!(w.crossed >= 1 && w.crossed == w.walked as u32, "steps are the CU key");
        }
        let ol = leg(&om, zfo, &src(oa), u).unwrap();
        let starts = clmm::whirl_leg_starts(&accts[&om.pool].data, zfo).unwrap();
        for st in starts { assert!(oa.iter().any(|(i, k)| *i == st as i64 && accts.contains_key(k)), "{st} held or known absent"); }
        assert!(ol.clmm_arrays(1_000).is_none());
    }
    // a size search over the pair (the mints: DCAL token0 = WSOL, 4uny a = WSOL): buy J6pQ on one, sell on the other
    let ladder: Vec<u64> = [0.01, 0.05, 0.1, 0.5].iter().map(|s| (s * 1e9) as u64).collect();
    for (b, zb, s, zs) in [(&rm, true, &om, false), (&om, true, &rm, false)] {
        let (ba, sa) = if b.venue == Venue::RayClmm { (ra, oa) } else { (oa, ra) };
        let (lb, ls) = (leg(b, zb, &src(ba), u).unwrap(), leg(s, zs, &src(sa), u).unwrap());
        // the size search's pick is the exact round trip at its size
        let t = best(&lb, &ls, &ladder, 1_000_000, 500_000_000).unwrap();
        assert_eq!(round_trip(&lb, &ls, t.x).unwrap(), t);
    }
    // a Whirlpool leg whose needed array is not known (not read, not known absent) is a missing account, not a zeroed one
    let mut gone = accts.clone();
    let st = clmm::whirl_leg_starts(&accts[&om.pool].data, true).unwrap()[1];
    let k = oa.iter().find(|(i, _)| *i == st as i64).unwrap().1;
    gone.remove(&k);
    let getg = |k: &Pk| gone.get(k);
    let r = leg(&om, true, &Src { get: &getg, arrays: oa, usable: &all, clock: clock(orca.slot, unix) }, u);
    assert_eq!(r.err(), Some(Why::ClmmArray));
}

// ------------------------------------------------------------------------------------------------ no panics

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 { self.0 ^= self.0 << 13; self.0 ^= self.0 >> 7; self.0 ^= self.0 << 17; self.0 }
    fn below(&mut self, n: u64) -> u64 { self.next() % n.max(1) }
}

/// The quote path never panics (PLAN-ADDENDUM WP-21; arbx-sizing "no panics on any input"): every fixture pool, both
/// directions, with random bytes of the pool, its config / extension / oracle, its tick arrays and its vaults rewritten
/// (0xFF runs, zeroes, random), then `quote::leg` for a route and a third party's swap, exact quotes at sizes from 1 to
/// u64::MAX, the walk, the builder's tick arrays, exact out, the size search and the accuracy monitor's prediction: each
/// either answers or refuses
#[test]
fn clmm_quote_path_never_panics() {
    let mut rng = Rng(0x9E37_79B9_7F4A_7C15);
    let mut runs = 0usize;
    let mut answered = 0usize;
    let mut pools: Vec<&Fx> = fixtures().values().collect();
    pools.sort_by_key(|f| f.pool);
    for fx in pools {
        let m = meta(fx);
        let base = accounts(fx, &Value::Null);
        let arrays = followed(fx, &m, &base);
        let mut keys: Vec<Pk> = base.keys().copied().collect();
        keys.sort();
        for it in 0..150 {
            let mut accts = base.clone();
            for _ in 0..1 + rng.below(4) {
                let k = keys[rng.below(keys.len() as u64) as usize];
                let mut d = accts[&k].data.to_vec();
                if d.is_empty() { continue; }
                let at = rng.below(d.len() as u64) as usize;
                let n = (1 + rng.below(16) as usize).min(d.len() - at);
                for b in &mut d[at..at + n] { *b = match it % 3 { 0 => 0xFF, 1 => 0, _ => rng.next() as u8 }; }
                accts.insert(k, Acct::rpc(Arc::from(d), fx.slot, 0, 0, asrc::RPC_BOOT));
            }
            let get = |k: &Pk| accts.get(k);
            for zfo in [true, false] {
                for u in [Use::Route { dlmm_budget: DLMM_BUDGET_ALONE }, Use::Third] {
                    let unix = if it % 7 == 0 { i64::MAX - rng.below(100) as i64 } else { fx.unix + rng.below(100_000) as i64 - 50_000 };
                    let src = Src { get: &get, arrays: &arrays, usable: &|_| true, clock: clock(fx.slot, unix) };
                    runs += 1;
                    let Ok(l) = leg(&m, zfo, &src, u) else { continue };
                    answered += 1;
                    for x in [0u64, 1, 1_000, 1_000_000_000, 1 + rng.below(u64::MAX - 1), u64::MAX] {
                        let _ = l.quote(x);
                        let _ = l.walk(x);
                        let _ = l.clmm_arrays(x);
                        let _ = l.exact_out(x);
                    }
                    let _ = best(&l, &l, &[1_000, 1_000_000, 1_000_000_000], 1, u64::MAX / 2);
                }
                let v = accuracy::View { get: &get, arrays: &arrays, now_unix: fx.unix, slot: fx.slot };
                let _ = accuracy::predict(&m, &v, zfo, 1 + rng.below(1 << 40), it % 2 == 0);
            }
        }
    }
    eprintln!("{runs} mutated legs, {answered} parsed, quoted at every size without a panic");
    assert!(runs > 10_000 && answered > 1_000, "{runs} {answered}");
}

/// Orca's U256 division as deployed (`U256Muldiv::div`, Knuth D with a carry word: DESIGN.md §2.9, §7 item 12): never a
/// panic. Against a 256-bit long division on random and edge-limbed operands (the add-back and qhat-correction paths of
/// Knuth D need such limbs): equal wherever it answers; None only where the deployed binary panics (the add-back that
/// reads past the top word, fixed upstream in 4aac511 after this deploy) or the divisor is zero. A swap step reads None as
/// TooLarge, so the engine refuses the size (`unquotable_clmm`) where the program would fail
#[test]
fn orca_u256_division_refuses_never_panics() {
    use arbx_sizing::venue::orca_whirlpool::muldiv_div_as_deployed as div;
    // reference: 256-bit binary long division
    fn reference(n: [u64; 4], d: [u64; 4]) -> ([u64; 4], [u64; 4]) {
        let (mut q, mut r) = ([0u64; 4], [0u64; 4]);
        let ge = |a: &[u64; 4], b: &[u64; 4]| { for i in (0..4).rev() { if a[i] != b[i] { return a[i] > b[i]; } } true };
        for bit in (0..256).rev() {
            // r = r << 1 | bit of n
            let mut carry = (n[bit / 64] >> (bit % 64)) & 1;
            for w in r.iter_mut() { let nc = *w >> 63; *w = (*w << 1) | carry; carry = nc; }
            if carry == 1 || ge(&r, &d) {
                let mut borrow = 0u128;
                for i in 0..4 { let t = (r[i] as u128).wrapping_sub(d[i] as u128).wrapping_sub(borrow); r[i] = t as u64; borrow = (t >> 127) & 1; }
                q[bit / 64] |= 1 << (bit % 64);
            }
        }
        (q, r)
    }
    let mut rng = Rng(0xD1B5_4A32_D192_ED03);
    let edge = [0u64, 1, 2, (1 << 63) - 1, 1 << 63, u64::MAX - 1, u64::MAX];
    let (mut ok, mut none) = (0usize, 0usize);
    for i in 0..200_000 {
        let mut limb = |r: &mut Rng| if r.below(3) == 0 { r.next() } else { edge[r.below(edge.len() as u64) as usize] };
        let n = [limb(&mut rng), limb(&mut rng), limb(&mut rng), limb(&mut rng)];
        let mut d = [limb(&mut rng), limb(&mut rng), limb(&mut rng), if i % 2 == 0 { 0 } else { limb(&mut rng) }];
        if i % 5 == 0 { d[2] = 0; d[3] = 0; }
        match div(n, d) {
            Some((q, r)) => { assert!(d != [0; 4]); assert_eq!((q, r), reference(n, d), "n={n:?} d={d:?}"); ok += 1; }
            None => none += 1,
        }
    }
    eprintln!("Orca U256Muldiv::div as deployed: {ok} exact, {none} refused (zero divisor or the deployed add-back read)");
    assert!(ok > 150_000);
    assert_eq!(div([5, 0, 0, 0], [0; 4]), None, "a zero divisor refuses");
}
