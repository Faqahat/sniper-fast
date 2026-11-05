//! APEX-PROBE pure logic (no I/O, no clock): watchlist parsing, caps + per-fire gate, launch filter, guard prices,
//! the slot-guard instruction, tip groups, route specs, and the landing-position analysis. Everything here is unit-tested
//! (tests.rs); main.rs only wires it to the feeds, the RPC and the send paths.

use arbx::build::{self, Ix, Meta};
use arbx::snipe::{self, Launch};
use arbx::snipe_build;
use arbx::tx::{pk, Pk};
use std::collections::{HashMap, HashSet};

pub const LAMPORTS: f64 = 1e9;

// ------------------------------------------------------------------------------------------------------------------
// watchlist
// ------------------------------------------------------------------------------------------------------------------

pub fn parse_pk(s: &str) -> Option<Pk> {
    let s = s.trim();
    if s.len() < 32 || s.len() > 44 { return None; }
    bs58::decode(s).into_vec().ok().and_then(|v| v.try_into().ok())
}

/// The APEX watchlist: a JSON list of creator pubkeys (strings), or of objects with a "creator" field, or an object
/// holding such a list under "creators" / "watchlist" / "list"; or plain text, one pubkey per line (# comments). Entries
/// that are not pubkeys are an error (a typo must not silently shrink the list).
pub fn parse_watchlist(text: &str) -> Result<HashSet<Pk>, String> {
    let t = text.trim();
    let mut out = HashSet::new();
    if t.starts_with('[') || t.starts_with('{') {
        let v: serde_json::Value = serde_json::from_str(t).map_err(|e| format!("not valid JSON: {e}"))?;
        let list = match &v {
            serde_json::Value::Array(a) => a.clone(),
            serde_json::Value::Object(o) => ["creators", "watchlist", "list"].iter().find_map(|k| o.get(*k).and_then(|x| x.as_array()).cloned())
                .ok_or("JSON object without a creators / watchlist / list array")?,
            _ => return Err("JSON is neither a list nor an object".into()),
        };
        for (i, e) in list.iter().enumerate() {
            let s = match e {
                serde_json::Value::String(s) => s.as_str(),
                serde_json::Value::Object(o) => o.get("creator").and_then(|x| x.as_str()).ok_or(format!("entry {i}: object without a \"creator\" string"))?,
                _ => return Err(format!("entry {i}: neither a string nor an object")),
            };
            out.insert(parse_pk(s).ok_or(format!("entry {i}: '{s}' is not a base58 pubkey"))?);
        }
    } else {
        for (n, l) in t.lines().enumerate() {
            let s = l.split('#').next().unwrap_or("").trim().trim_matches(',').trim_matches('"');
            if s.is_empty() { continue; }
            out.insert(parse_pk(s).ok_or(format!("line {}: '{s}' is not a base58 pubkey", n + 1))?);
        }
    }
    Ok(out)
}

/// Which key of a create is matched against the watchlist.
/// APEX-PROBE-FIX (11-04): `creator` is now the pump.fun CreateEvent's `creator` field, the key the APEX backtests
/// (x1_extract / s3_sim / ev3.watch) attribute every launch to. It equals the create args' creator EXCEPT on holder-reward
/// launches (create_v2 is_holder_reward), where the program records the PDA ["holder-rewards", mint] (pump program) as the
/// creator: 3405 of 18901 launches on 11-03 (all 9 live r10/r11 fills that were not backtest picks). The args' creator
/// (the old `creator` match, == the signer on those 9) is `args`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MatchOn { Creator, Args, Signer, Either }

impl MatchOn {
    pub fn parse(s: &str) -> Result<MatchOn, String> {
        match s {
            "creator" => Ok(MatchOn::Creator), "args" => Ok(MatchOn::Args), "signer" => Ok(MatchOn::Signer), "either" => Ok(MatchOn::Either),
            _ => Err(format!("--match {s}: creator|args|signer|either")),
        }
    }
    /// the watchlist key that matched (None = not watched). `ev` = CreateEvent creator ([`event_creator`]), `args` = the
    /// create args' creator, `signer` = the fee payer. either = CreateEvent creator or signer.
    pub fn key(self, w: &HashSet<Pk>, ev: &Pk, args: &Pk, signer: Option<&Pk>) -> Option<Pk> {
        let s = signer.filter(|s| w.contains(*s)).copied();
        match self {
            MatchOn::Creator => w.contains(ev).then_some(*ev),
            MatchOn::Args => w.contains(args).then_some(*args),
            MatchOn::Signer => s,
            MatchOn::Either => if w.contains(ev) { Some(*ev) } else { s },
        }
    }
    pub fn hit(self, w: &HashSet<Pk>, ev: &Pk, args: &Pk, signer: Option<&Pk>) -> bool { self.key(w, ev, args, signer).is_some() }
}

/// the PDA pump.fun records as the creator of a holder-reward launch
pub fn holder_rewards_pda(mint: &Pk) -> Pk { arbx::pda::find_program_address(&[b"holder-rewards", mint], &snipe::PUMP).0 }

/// the CreateEvent's `creator` of a detected launch (shreds carry no logs, so it is derived from the create's args):
/// holder-reward launch -> PDA ["holder-rewards", mint]; otherwise the args' creator. Checked on the 11-03 tape (18,901
/// creates): event creator == the create's user on 15,372; of the 3,529 others, 3,405 are the holder-rewards PDA of the
/// mint and 124 an args creator != signer; raw txs (RPC) of 15 creates confirm the args/flag side of each kind (tests.rs
/// replays real ones).
pub fn event_creator(l: &Launch) -> Pk { if l.is_holder_reward { holder_rewards_pda(&l.mint) } else { l.creator } }

// ------------------------------------------------------------------------------------------------------------------
// caps and the per-fire gate
// ------------------------------------------------------------------------------------------------------------------

/// The raw cap arguments (SOL / minutes as typed)
#[derive(Clone, Debug)]
pub struct CapArgs {
    pub live: bool,
    pub size_sol: f64,
    pub max_buys: u32,
    pub max_spend_sol: f64,
    pub kill_below_sol: Option<f64>,
    pub max_runtime_min: Option<f64>,
    pub max_open: usize,
    pub buy_guard: f64,
    pub sell_guard: f64,
    pub hold_ms: u64,
}

/// Validated caps (lamports)
#[derive(Clone, Debug, PartialEq)]
pub struct Caps {
    pub size: u64,
    pub max_buys: u32,
    pub max_spend: u64,
    pub kill_below: Option<u64>,
    pub max_runtime_s: Option<u64>,
    pub max_open: usize,
    pub buy_guard: f64,
    pub sell_guard: f64,
    pub hold_ms: u64,
}

pub const MAX_SIZE_SOL: f64 = 0.25; // owner 11-03 ~23:30 PKT: probe 2 at 0.2 SOL (was 0.1)
pub const MAX_SPEND_HARD_SOL: f64 = 5.0;

/// Refusal logic for the start. Live needs every cap explicitly bounded: --kill-below and --max-runtime-min have no
/// default and must be given; the others have the owner's defaults (size 0.05 <= 0.25, 20 buys, 1.5 SOL at risk).
pub fn validate_caps(a: &CapArgs) -> Result<Caps, String> {
    let fin = |x: f64, n: &str| if x.is_finite() { Ok(x) } else { Err(format!("{n}: not a number")) };
    let size = fin(a.size_sol, "--size-sol")?;
    if !(size > 0.0 && size <= MAX_SIZE_SOL + 1e-12) { return Err(format!("--size-sol {size}: must be > 0 and <= {MAX_SIZE_SOL}")); }
    if a.max_buys == 0 || a.max_buys > 200 { return Err(format!("--max-buys {}: must be 1..200", a.max_buys)); }
    let spend = fin(a.max_spend_sol, "--max-spend-sol")?;
    if !(spend > 0.0 && spend <= MAX_SPEND_HARD_SOL) { return Err(format!("--max-spend-sol {spend}: must be > 0 and <= {MAX_SPEND_HARD_SOL}")); }
    if spend < size * 1.1 { return Err(format!("--max-spend-sol {spend} is below one buy plus fees ({:.4})", size * 1.1)); }
    if a.max_open == 0 || a.max_open > 3 { return Err(format!("--max-open {}: must be 1..3", a.max_open)); }
    if !(0.0..=1.0).contains(&a.buy_guard) { return Err(format!("--buy-guard {}: must be 0..1 (0.2 = pay at most 20% above the expected price)", a.buy_guard)); }
    if !(0.0..=1.0).contains(&a.sell_guard) { return Err(format!("--sell-guard {}: must be 0..1 (0.5 = accept down to 50% of the expected SOL)", a.sell_guard)); }
    if a.hold_ms < 100 || a.hold_ms > 600_000 { return Err(format!("--hold-ms {}: must be 100..600000", a.hold_ms)); }
    let kill = match a.kill_below_sol {
        Some(k) => { let k = fin(k, "--kill-below")?; if k <= 0.0 { return Err("--kill-below must be > 0".into()); } Some((k * LAMPORTS) as u64) }
        None if a.live => return Err("live mode needs --kill-below SOL (stop when the wallet balance is under it)".into()),
        None => None,
    };
    let rt = match a.max_runtime_min {
        Some(m) => { let m = fin(m, "--max-runtime-min")?; if !(m > 0.0 && m <= 10_080.0) { return Err("--max-runtime-min must be > 0 and <= 10080".into()); } Some((m * 60.0) as u64) }
        None if a.live => return Err("live mode needs --max-runtime-min".into()),
        None => None,
    };
    Ok(Caps { size: (size * LAMPORTS).round() as u64, max_buys: a.max_buys, max_spend: (spend * LAMPORTS).round() as u64, kill_below: kill, max_runtime_s: rt,
        max_open: a.max_open, buy_guard: a.buy_guard, sell_guard: a.sell_guard, hold_ms: a.hold_ms })
}

/// What the run has used so far
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Ledger {
    pub buys_fired: u32,
    pub open: usize,
    /// worst-case cost of the open positions (lamports): released when a position closes
    pub open_worst: u64,
    /// sum of the closed trades' realized P&L (lamports, from the actual balance changes)
    pub realized: i64,
}

impl Ledger {
    /// SOL at risk now: the realized net loss (never negative) plus the open positions' worst case
    pub fn at_risk(&self) -> u64 { (-self.realized).max(0) as u64 + self.open_worst }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Gate { Go, Skip(&'static str), Stop(&'static str) }

/// The per-fire gate (no I/O: the balance is the poller's last value, None = unknown). Stop = no buy can ever pass
/// again in this run (the caller stops new buys); Skip = this one only.
pub fn gate(c: &Caps, l: &Ledger, worst: u64, live: bool, balance: Option<u64>, runtime_s: u64, stopping: bool) -> Gate {
    if stopping { return Gate::Skip("stopping"); }
    if c.max_runtime_s.is_some_and(|m| runtime_s >= m) { return Gate::Stop("max_runtime"); }
    if l.buys_fired >= c.max_buys { return Gate::Stop("max_buys"); }
    if l.at_risk().saturating_add(worst) > c.max_spend {
        return if l.open == 0 { Gate::Stop("max_spend") } else { Gate::Skip("max_spend_open") };
    }
    if l.open >= c.max_open { return Gate::Skip("position_open"); }
    if live {
        let Some(b) = balance else { return Gate::Skip("balance_unknown") };
        if let Some(k) = c.kill_below {
            if b < k { return Gate::Stop("kill_below"); }
            if b < k.saturating_add(worst) { return Gate::Skip("would_cross_kill_below"); }
        }
    }
    Gate::Go
}

/// rent of a Token-2022 ATA with the immutable-owner extension (what the buy's idempotent create pays) + a WSOL ATA,
/// counted in the worst case (it comes back when the ATA closes)
pub const RENT_ALLOW: u64 = 4_200_000;

/// worst-case lamports one round trip can take from the wallet: the size, every tip of the buy and of the sell retries,
/// priority + base fees, the ATA rents
pub fn worst_cost(size: u64, buy_tips: u64, cu_limit: u32, cu_price: u64, sell_tips: u64, sell_cu_limit: u32, sell_cu_price: u64, sell_tries: u64) -> u64 {
    let prio = |cu: u32, p: u64| (cu as u128 * p as u128 / 1_000_000) as u64;
    size + buy_tips + prio(cu_limit, cu_price) + 5_000 + RENT_ALLOW + sell_tries.max(1) * (sell_tips + prio(sell_cu_limit, sell_cu_price) + 5_000)
}

// ------------------------------------------------------------------------------------------------------------------
// launch filter + guard prices
// ------------------------------------------------------------------------------------------------------------------

/// Why a watched create is not bought (APEX: non-Mayhem SOL-quote curves only)
pub fn skip_reason(l: &Launch, sol_quote: bool, legacy_ok: bool, allow_mayhem: bool) -> Option<&'static str> {
    if !sol_quote { return Some("non_sol_quote"); }
    if l.is_mayhem && !allow_mayhem { return Some("mayhem"); }
    if l.creator_fee_bps > 0 { return Some("creator_fee"); }
    if !l.is_create_v2 && !legacy_ok { return Some("legacy_create"); }
    None
}

/// SOL into the curve net of pump's fee
pub fn net_of_fee(sol_in: u64) -> u64 { (sol_in as u128 * 10_000 / (10_000 + snipe::PUMP_FEE_BPS) as u128) as u64 }

/// Tokens our `spend` buys right after the create tx's dev buy(s) (`dev_lamports` = curve SOL of the dev buys), on the
/// fresh constant-product curve
pub fn expected_tokens(dev_lamports: u64, spend: u64) -> u64 {
    snipe::curve_tokens_out(snipe::CURVE_VQ0.saturating_add(dev_lamports), net_of_fee(spend))
}

/// The buy's min_tokens_out: the expected tokens at a price `guard` above the expected one (0.2 = at most 20% more)
pub fn buy_min_out(expected: u64, guard: f64) -> u64 { ((expected as f64) / (1.0 + guard)).floor().max(1.0) as u64 }

/// The SOL `amount` tokens sell for on a curve at virtual reserves (vsol, vtok), net of pump's fee
pub fn sell_expected(vsol: u64, vtok: u64, amount: u64) -> u64 {
    if vsol == 0 || vtok == 0 { return 0; }
    let k = vsol as u128 * vtok as u128;
    let nv = k.div_ceil(vtok as u128 + amount as u128);
    let gross = (vsol as u128).saturating_sub(nv) as u64;
    (gross as u128 * 10_000 / (10_000 + snipe::PUMP_FEE_BPS) as u128) as u64
}

/// The sell's min SOL out: the expected SOL less `guard` (0.5 = accept down to half). 0 when nothing is known.
pub fn sell_min_out(expected: u64, guard: f64) -> u64 { ((expected as f64) * (1.0 - guard)).floor().max(0.0) as u64 }

// ------------------------------------------------------------------------------------------------------------------
// instructions
// ------------------------------------------------------------------------------------------------------------------

/// Lighthouse (L2TExMFK...): AssertSysvarClock = the on-chain slot deadline the dip engine uses (--buy-max-slot-delta)
pub static LIGHTHOUSE: std::sync::LazyLock<Pk> = std::sync::LazyLock::new(|| pk("L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"));

/// a verified guard encoding (ix discriminator, integer operator, whether the program is passed as account 0)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GuardEnc { pub disc: u8, pub op: u8, pub acct: bool }

/// the encoding in our own landed PROD buys (AMS run 48: Lighthouse data 0f 00 00 <slot u64> 05); the start-up simulation
/// verifies it on mainnet (tried first), shadow falls back to it
pub const GUARD_DEFAULT: GuardEnc = GuardEnc { disc: 15, op: 5, acct: false };

pub fn guard_ix(g: GuardEnc, deadline: u64) -> Ix {
    let mut d = vec![g.disc, 0, 0];
    d.extend(deadline.to_le_bytes());
    d.push(g.op);
    Ix { program: *LIGHTHOUSE, accounts: if g.acct { vec![Meta { key: *LIGHTHOUSE, signer: false, writable: false }] } else { vec![] }, data: d }
}

/// insert the slot guard right before the pump buy instruction
pub fn insert_guard(mut ixs: Vec<Ix>, g: GuardEnc, deadline: u64) -> Vec<Ix> {
    let at = ixs.iter().position(|ix| ix.program == *snipe::PUMP).unwrap_or(ixs.len());
    ixs.insert(at, guard_ix(g, deadline));
    ixs
}

/// One buy variant's instruction list, as the dip engine sends its buys: [AdvanceNonce (nonce mode)] > [tip transfers] >
/// CU limit > CU price > base ATA (T22, idempotent) > WSOL ATA (idempotent) > [slot guard] > buy_exact_quote_in_v3.
/// No wrap (v3 SOL trades settle in native SOL). More than 2 System tips raise the CU limit by 300 each (lat::build_tx).
#[allow(clippy::too_many_arguments)]
pub fn buy_ixs(user: Pk, l: &Launch, spend: u64, min_out: u64, cu_limit: u32, cu_price: u64, nonce: Option<Pk>, tips: &[(Pk, u64)], guard: Option<(GuardEnc, u64)>) -> Vec<Ix> {
    let plan = snipe_build::BuyPlan { spend_lamports: spend, min_tokens_out: min_out, cu_limit, cu_price_micro: cu_price, create_ata: true, track_volume: true,
        nonce: nonce.map(|n| (n, user)), wrap: false };
    let mut ixs = snipe_build::buy_message_ixs(user, l, &plan);
    if let Some((g, dl)) = guard { ixs = insert_guard(ixs, g, dl); }
    let at = if nonce.is_some() { 1 } else { 0 };
    for (i, (t, lam)) in tips.iter().enumerate() { ixs.insert(at + i, build::transfer_ix(user, *t, *lam)); }
    if tips.len() > 2 { bump_cu_limit(&mut ixs, 300 * (tips.len() as u32 - 2)); }
    ixs
}

/// raise the SetComputeUnitLimit ix by `extra` units
pub fn bump_cu_limit(ixs: &mut [Ix], extra: u32) {
    for ix in ixs.iter_mut() {
        if ix.program == arbx::tx::COMPUTE_BUDGET && ix.data.len() == 5 && ix.data[0] == 2 {
            let cur = u32::from_le_bytes(ix.data[1..5].try_into().unwrap());
            ix.data[1..5].copy_from_slice(&cur.saturating_add(extra).min(1_400_000).to_le_bytes());
            return;
        }
    }
}

/// The sell: CU limit > CU price > [tips] > sell_v3 (all tokens) > close the base ATA (rent back). The WSOL ATA is never
/// closed (no wrap; it may be shared with the dip engine on the same wallet).
pub fn sell_ixs(user: Pk, l: &Launch, amount: u64, min_sol: u64, cu_limit: u32, cu_price: u64, tips: &[(Pk, u64)]) -> Vec<Ix> {
    let mut ixs = snipe_build::sell_message_ixs(user, l, amount, min_sol, cu_limit, cu_price, false);
    let at = ixs.iter().position(|ix| ix.program == *snipe::PUMP).unwrap_or(0);
    for (i, (t, lam)) in tips.iter().enumerate() { ixs.insert(at + i, build::transfer_ix(user, *t, *lam)); }
    if tips.len() > 2 { bump_cu_limit(&mut ixs, 300 * (tips.len() as u32 - 2)); }
    ixs
}

// ------------------------------------------------------------------------------------------------------------------
// routes + tips
// ------------------------------------------------------------------------------------------------------------------

pub const CLASSES: [&str; 6] = ["bam", "harmonic", "jito", "fd", "agave", "other"];

/// leader class of a getClusterNodes clientId (the dip engine's lat::class)
pub fn class(client: &str) -> &'static str {
    match client {
        "AgaveBam" | "FireBAM" => "bam",
        c if c.starts_with("Harmonic") => "harmonic",
        "JitoLabs" => "jito",
        "Firedancer" | "Frankendancer" => "fd",
        "Agave" => "agave",
        "" => "unknown",
        _ => "other",
    }
}

/// the dip engine's route presets (ops/prod/run_dip_prod.sh --routes vN)
pub fn route_preset(name: &str) -> Option<&'static str> {
    Some(match name {
        "v13" => "bam=nozomi+helius-swqos+bolt+falcon+falcon-udp+soyas+solami+0slot;jito=solami+soyas+glaive+falcon+falcon-udp+helius-swqos+0slot;harmonic=nozomi+landx-fra3+falcon+falcon-udp+glaive+soyas+solami+0slot;fd=0slot+nozomi+landx-fra3+staked-rpc+soyas+solami;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
        "v12" => "bam=nozomi+helius-swqos+bolt+falcon+falcon-udp+soyas+solami;jito=solami+soyas+glaive+falcon+falcon-udp+helius-swqos;harmonic=nozomi+landx-fra3+falcon+falcon-udp+glaive+soyas+solami;fd=nozomi+landx-fra3+staked-rpc+soyas+solami;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
        "v9" => "bam=nozomi+helius-swqos+bolt;jito=helius+helius-swqos+staked-rpc;harmonic=nozomi+landx-fra3;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
        "v8" => "bam=nozomi+helius-swqos+bolt+staked-rpc;jito=helius+nozomi+jito-bundle+staked-rpc;harmonic=nozomi+helius-swqos+landx-fra3+staked-rpc;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
        _ => return None,
    })
}

/// "class=a+b;class=...;default=..." (or a preset name) -> class -> path names (order kept, duplicates dropped)
pub fn parse_route_spec(spec: &str) -> Result<HashMap<String, Vec<String>>, String> {
    let spec = route_preset(spec).unwrap_or(spec);
    let mut m: HashMap<String, Vec<String>> = HashMap::new();
    for part in spec.split(';').map(str::trim).filter(|s| !s.is_empty()) {
        let (c, list) = part.split_once('=').ok_or(format!("--routes: '{part}' is not class=path+path"))?;
        let c = c.trim();
        if c != "default" && !CLASSES.contains(&c) { return Err(format!("--routes: unknown class '{c}' (use {} or default)", CLASSES.join("|"))); }
        let mut v: Vec<String> = Vec::new();
        for n in list.split(['+', ',']).map(str::trim).filter(|s| !s.is_empty()) { if !v.iter().any(|x| x == n) { v.push(n.to_string()); } }
        if v.is_empty() { return Err(format!("--routes: class '{c}' has no path")); }
        m.insert(c.to_string(), v);
    }
    if !m.contains_key("default") { return Err("--routes needs a default=... entry".into()); }
    Ok(m)
}

/// every path name a route map uses
pub fn route_names(m: &HashMap<String, Vec<String>>) -> Vec<String> {
    let mut v: Vec<String> = m.values().flatten().cloned().collect();
    v.sort();
    v.dedup();
    v
}

/// the classes a buy for a create in a slot led by `c0` goes to: its leader's, plus the next leader's when the slot is
/// the leader's last (`next` = Some(class of slot+1's leader) only then); `no_union_harmonic`: not when c0 is harmonic
pub fn route_classes(c0: Option<&'static str>, next: Option<&'static str>, no_union_harmonic: bool) -> Vec<&'static str> {
    let mut v: Vec<&'static str> = Vec::new();
    if let Some(c) = c0 { v.push(c); }
    let skip = no_union_harmonic && c0 == Some("harmonic");
    if let (false, Some(n)) = (skip, next) { if !v.contains(&n) { v.push(n); } }
    v
}

/// tip groups of a fan (the dip engine's fastfire::tip_groups): a tipped path joins the first group whose tip account is
/// one of ITS accounts (one tip family; the group pays the larger amount), else opens its own; tipless paths share one
/// tipless group. -> (tip, fan indices) per group, first-appearance order
pub fn tip_groups(paths: &[(Option<(Pk, u64)>, &[Pk])]) -> Vec<(Option<(Pk, u64)>, Vec<usize>)> {
    let mut g: Vec<(Option<(Pk, u64)>, Vec<usize>)> = Vec::new();
    for (i, (tip, accts)) in paths.iter().enumerate() {
        match tip.filter(|t| t.1 > 0) {
            None => match g.iter_mut().find(|x| x.0.is_none()) { Some(x) => x.1.push(i), None => g.push((None, vec![i])) },
            Some((t, l)) => match g.iter_mut().find(|x| x.0.is_some_and(|(a, _)| accts.contains(&a))) {
                Some(x) => { if let Some(e) = x.0.as_mut() { e.1 = e.1.max(l); } x.1.push(i); }
                None => g.push((Some((t, l)), vec![i])),
            },
        }
    }
    g
}

// ------------------------------------------------------------------------------------------------------------------
// landing position (from the executed feed's records of the mint, or a getBlock read)
// ------------------------------------------------------------------------------------------------------------------

/// one executed tx that touched the mint
#[derive(Clone, Debug, PartialEq)]
pub struct ExecRec {
    pub slot: u64,
    pub index: u64,
    pub sig: [u8; 64],
    pub ok: bool,
    pub is_create: bool,
    /// (buyer, curve SOL, tokens) of each buy TradeEvent on the mint
    pub buys: Vec<(Pk, u64, u64)>,
    pub sells: usize,
}

#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct Position {
    pub create_slot: u64,
    pub create_idx: u64,
    pub land_slot: u64,
    pub land_idx: u64,
    pub slot_delta: i64,
    /// our block index minus the create's (same slot only)
    pub idx_delta: Option<i64>,
    /// buy TradeEvents inside the create tx (dev buy / bundled in the same tx)
    pub dev_buys_in_create: usize,
    /// txs on the mint strictly between the create and us (any kind)
    pub txs_between: usize,
    /// txs with >= 1 buy between the create and us, their distinct buyers, and the curve SOL they put in
    pub buy_txs_ahead: usize,
    pub buyers_ahead: usize,
    pub sol_ahead: u64,
    pub sells_ahead: usize,
    /// our place among all buy txs after the create (1 = the first buyer after the create tx)
    pub buy_rank: usize,
}

/// Where we landed relative to the create and the other buyers. None when the create or our tx is not in `recs`.
pub fn position(recs: &[ExecRec], create_sig: Option<&[u8; 64]>, our_sig: &[u8; 64], us: &Pk) -> Option<Position> {
    let mut v: Vec<&ExecRec> = recs.iter().collect();
    v.sort_by_key(|r| (r.slot, r.index));
    v.dedup_by_key(|r| (r.slot, r.index));
    let c = v.iter().position(|r| r.is_create || create_sig.is_some_and(|s| *s == r.sig))?;
    let o = v.iter().position(|r| r.sig == *our_sig)?;
    let (cr, or) = (v[c], v[o]);
    let mut p = Position { create_slot: cr.slot, create_idx: cr.index, land_slot: or.slot, land_idx: or.index, slot_delta: or.slot as i64 - cr.slot as i64,
        idx_delta: (or.slot == cr.slot).then(|| or.index as i64 - cr.index as i64), dev_buys_in_create: cr.buys.len(), txs_between: 0, buy_txs_ahead: 0,
        buyers_ahead: 0, sol_ahead: 0, sells_ahead: 0, buy_rank: 0 };
    if o > c {
        let mut who: HashSet<Pk> = HashSet::new();
        for r in &v[c + 1..o] {
            if !r.ok { continue; }
            p.txs_between += 1;
            let theirs: Vec<_> = r.buys.iter().filter(|b| b.0 != *us).collect();
            if !theirs.is_empty() { p.buy_txs_ahead += 1; }
            for b in theirs { who.insert(b.0); p.sol_ahead += b.1; }
            p.sells_ahead += r.sells;
        }
        p.buyers_ahead = who.len();
        p.buy_rank = p.buy_txs_ahead + 1;
    }
    Some(p)
}

// ------------------------------------------------------------------------------------------------------------------
// signed copies of one buy
// ------------------------------------------------------------------------------------------------------------------

/// one signed copy of a buy and the fan paths (indices) it goes to
#[derive(Clone, Debug)]
pub struct Copy { pub raw: Vec<u8>, pub sig: [u8; 64], pub paths: Vec<usize>, pub tip: u64 }

pub fn sig_of(raw: &[u8]) -> [u8; 64] {
    let mut s = [0u8; 64];
    if raw.len() >= 65 { s.copy_from_slice(&raw[1..65]); }
    s
}

/// What one buy needs besides the launch
#[derive(Clone, Copy, Debug)]
pub struct BuyCfg { pub user: Pk, pub spend: u64, pub min_out: u64, pub cu_limit: u32, pub cu_price: u64, pub guard: Option<(GuardEnc, u64)> }

/// The signed copies of one buy for a fan whose paths form `groups` (tip_groups):
///  - no nonce: ONE tx carrying one tip per group (lat::build_tx); over 1232 bytes drops the last group until it fits;
///  - nonce (account, stored value): one variant per group, each AdvanceNonce + only its own tip (at most one lands, a
///    landed buy pays one tip), the nonce value as the blockhash.
pub fn build_copies(key: &ed25519_dalek::SigningKey, c: &BuyCfg, l: &Launch, bh: [u8; 32], nonce: Option<(Pk, [u8; 32])>,
                    groups: &[(Option<(Pk, u64)>, Vec<usize>)]) -> Result<Vec<Copy>, String> {
    let sysvar_rb = pk("SysvarRecentB1ockHashes11111111111111111111");
    match nonce {
        None => {
            let mut n = groups.len();
            loop {
                let g = &groups[..n];
                let tips: Vec<(Pk, u64)> = g.iter().filter_map(|x| x.0).collect();
                let ixs = buy_ixs(c.user, l, c.spend, c.min_out, c.cu_limit, c.cu_price, None, &tips, c.guard);
                let msg = build::compile_v0(c.user, &ixs, bh, &[], &[])?;
                let raw = build::sign(&msg, key);
                if raw.len() <= 1232 || n <= 1 {
                    if raw.len() > 1232 { return Err(format!("buy tx {} bytes > 1232 even with one path group", raw.len())); }
                    let sig = sig_of(&raw);
                    return Ok(vec![Copy { raw, sig, paths: g.iter().flat_map(|x| x.1.iter().copied()).collect(), tip: tips.iter().map(|t| t.1).sum() }]);
                }
                n -= 1;
            }
        }
        Some((acct, value)) => {
            let mut out = Vec::with_capacity(groups.len());
            for (tip, idx) in groups {
                let tips: Vec<(Pk, u64)> = tip.iter().copied().collect();
                let ixs = buy_ixs(c.user, l, c.spend, c.min_out, c.cu_limit, c.cu_price, Some(acct), &tips, c.guard);
                let msg = build::compile_v0(c.user, &ixs, value, &[], &[acct, sysvar_rb])?;
                let raw = build::sign(&msg, key);
                if raw.len() > 1232 { return Err(format!("nonce variant {} bytes > 1232", raw.len())); }
                let sig = sig_of(&raw);
                out.push(Copy { raw, sig, paths: idx.clone(), tip: tip.map_or(0, |t| t.1) });
            }
            Ok(out)
        }
    }
}

/// A router (CPI) create as a Launch (the dip engine's router_launch): curve + ATA derived from the mint, creator from
/// the router args, dev = curve cost of min_tokens_out / 0.98
pub fn router_launch(tx: &arbx::tx::Tx) -> Option<Launch> {
    let (mint, creator, min_tokens, mayhem, holder) = snipe::router_create(tx)?;
    let mut l = snipe_build::launch_from_target(mint, creator);
    l.dev_buy_lamports = (snipe::curve_cost(snipe::CURVE_VQ0, min_tokens) as u128 * 100 / 98) as u64;
    l.is_mayhem = mayhem;
    l.is_holder_reward = holder;
    Some(l)
}

// ==================================================================================================================
// v2 (APEX-FEES recipe, 11-03): lanes (one durable-nonce copy per lane, ONE tip each), FIRST-OR-REVERT, attempt outcomes
// ==================================================================================================================

/// one lane entry of a class: a send path, its tip (None = the path's configured minimum) and the copy's priority fee in
/// lamports (None = --prio-lamports)
#[derive(Clone, Debug, PartialEq)]
pub struct LaneSpec { pub path: String, pub tip: Option<u64>, pub prio: Option<u64> }

/// the APEX-FEES recipe (sniper-data/apex2/fees/recipe.txt + lanes.txt): BAM / FireBAM / Jito leaders -> Jito tip 2 mSOL +
/// one no-tip high-priority copy (staked-rpc, 2 mSOL priority); Harmonic -> nozomi 2.5 mSOL; Firedancer -> astralane 2.5 mSOL
/// + 0.5 mSOL priority; the rest -> v13's lanes (nozomi, helius-swqos, bolt, staked-rpc), one tip each. No 0slot, no
/// helius on Harmonic / Firedancer. Every other copy's priority = --prio-lamports (0.1 mSOL: priority is paid on reverts).
pub const LANES_DEFAULT: &str = "bam=jito-bundle:2000000,staked-rpc:0@2000000;jito=jito-bundle:2000000,staked-rpc:0@2000000;\
harmonic=nozomi:2500000;fd=astralane:2500000@500000;agave=nozomi,helius-swqos,bolt,staked-rpc:0;other=nozomi,helius-swqos,bolt,staked-rpc:0;\
default=nozomi,helius-swqos,bolt,staked-rpc:0";

/// "class=path[:tip][@prio],path...;..." or a route preset (v8..v13: paths at their configured tips, default priority).
/// Duplicates within a class keep the first. Needs default=.
pub fn parse_lanes(spec: &str) -> Result<HashMap<String, Vec<LaneSpec>>, String> {
    let spec = route_preset(spec).unwrap_or(spec);
    let mut m: HashMap<String, Vec<LaneSpec>> = HashMap::new();
    for part in spec.split(';').map(str::trim).filter(|s| !s.is_empty()) {
        let (c, list) = part.split_once('=').ok_or(format!("lanes: '{part}' is not class=lane,lane"))?;
        let c = c.trim();
        if c != "default" && !CLASSES.contains(&c) { return Err(format!("lanes: unknown class '{c}' (use {} or default)", CLASSES.join("|"))); }
        let mut v: Vec<LaneSpec> = Vec::new();
        for e in list.split(['+', ',']).map(str::trim).filter(|s| !s.is_empty()) {
            let (head, prio) = match e.split_once('@') { Some((h, p)) => (h, Some(p.trim().parse::<u64>().map_err(|_| format!("lanes: '{e}': priority is not lamports"))?)), None => (e, None) };
            let (path, tip) = match head.split_once(':') { Some((n, t)) => (n.trim(), Some(t.trim().parse::<u64>().map_err(|_| format!("lanes: '{e}': tip is not lamports"))?)), None => (head.trim(), None) };
            if path.is_empty() { return Err(format!("lanes: '{e}': no path")); }
            if tip.is_some_and(|t| t > 20_000_000) || prio.is_some_and(|p| p > 20_000_000) { return Err(format!("lanes: '{e}': tip / priority above 0.02 SOL")); }
            if !v.iter().any(|x| x.path == path) { v.push(LaneSpec { path: path.to_string(), tip, prio }); }
        }
        if v.is_empty() { return Err(format!("lanes: class '{c}' has no lane")); }
        m.insert(c.to_string(), v);
    }
    if !m.contains_key("default") { return Err("lanes need a default=... entry".into()); }
    Ok(m)
}

/// CU price (micro-lamports / CU) that makes the priority fee `prio` lamports at `cu_limit`
pub fn cu_price_for(prio: u64, cu_limit: u32) -> u64 { (prio as u128 * 1_000_000 / cu_limit.max(1) as u128) as u64 }

/// one lane resolved for a buy: send path index, tip (account, lamports; None = a tipless copy), priority lamports
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LaneCopy { pub pi: usize, pub tip: Option<(Pk, u64)>, pub prio: u64 }

/// one durable-nonce variant per lane, each with ONLY its own tip and its own priority (at most one lands: they share the
/// nonce). Copy::paths = [that lane's path]
pub fn build_lane_copies(key: &ed25519_dalek::SigningKey, c: &BuyCfg, l: &Launch, nonce: (Pk, [u8; 32]), lanes: &[LaneCopy]) -> Result<Vec<Copy>, String> {
    let sysvar_rb = pk("SysvarRecentB1ockHashes11111111111111111111");
    let mut out = Vec::with_capacity(lanes.len());
    for ln in lanes {
        let tips: Vec<(Pk, u64)> = ln.tip.filter(|t| t.1 > 0).into_iter().collect();
        let ixs = buy_ixs(c.user, l, c.spend, c.min_out, c.cu_limit, cu_price_for(ln.prio, c.cu_limit), Some(nonce.0), &tips, c.guard);
        let msg = build::compile_v0(c.user, &ixs, nonce.1, &[], &[nonce.0, sysvar_rb])?;
        let raw = build::sign(&msg, key);
        if raw.len() > 1232 { return Err(format!("lane variant {} bytes > 1232", raw.len())); }
        let sig = sig_of(&raw);
        out.push(Copy { raw, sig, paths: vec![ln.pi], tip: tips.first().map_or(0, |t| t.1) });
    }
    Ok(out)
}

/// FIRST-OR-REVERT: the virtual SOL reserve after the create tx's dev buy(s) and the creator-bundle buys seen before we
/// sign, each leg priced exactly as pump does (exact-in: SOL in x 10000/10125 into the curve; cap: the token amount's curve
/// cost). None = a leg would fail / cannot be priced (then we do not know the state: no buy).
pub fn curve_after_legs(legs: &[(bool, u64, u64)]) -> Option<u64> {
    let sol = snipe::simulate_legs(snipe::CURVE_VQ0, legs)?;
    Some(snipe::CURVE_VQ0 + sol)
}

/// FIRST-OR-REVERT min_tokens_out: the tokens our spend buys at EXACTLY that state, less `tol` (0.005 = 0.5%: rounding;
/// a rival's buy of >= ~0.1 SOL ahead of us moves the price more and our buy reverts)
pub fn first_min_out(vq_state: u64, spend: u64, tol: f64) -> (u64, u64) {
    let exp = snipe::curve_tokens_out(vq_state, net_of_fee(spend));
    (exp, ((exp as f64) * (1.0 - tol)).floor().max(1.0) as u64)
}

/// (failed instruction index, custom error code) of a getTransaction / status `err`
pub fn err_code(err: &serde_json::Value) -> (Option<u64>, Option<u64>) {
    let ie = &err["InstructionError"];
    (ie[0].as_u64(), ie[1]["Custom"].as_u64())
}

/// the role of instruction `i` in one of our buy variants (to name a revert): nonce / tip / compute / ata / guard / buy
pub fn ix_role(raw: &[u8], i: u64) -> &'static str {
    let Some((tx, _)) = arbx::tx::parse_wire(raw) else { return "?" };
    let Some(ix) = tx.ixs.get(i as usize) else { return "?" };
    let p = tx.keys.get(ix.program as usize).copied().unwrap_or([0u8; 32]);
    if p == *snipe::PUMP { "buy" } else if p == *LIGHTHOUSE { "slot_guard" } else if p == *arbx::pda::ATA_PROGRAM { "ata" }
    else if p == arbx::tx::COMPUTE_BUDGET { "compute" } else if p == *arbx::pda::SYSTEM_PROGRAM { if ix.data.first() == Some(&4) { "nonce" } else { "tip" } } else { "other" }
}

/// the creator bundle of a create: the landed buys at the block indices right after the create's (create idx + 1, + 2, ...
/// with no gap; the study's rule, ops/strategies/apex2/fees/f2_build.py). -> (bundle tx count, their curve SOL)
pub fn bundle_after(recs: &[ExecRec], create: &ExecRec) -> (usize, u64, HashSet<[u8; 64]>) {
    let by: HashMap<u64, &ExecRec> = recs.iter().filter(|r| r.slot == create.slot && r.ok).map(|r| (r.index, r)).collect();
    let (mut i, mut n, mut sol, mut sigs) = (create.index, 0usize, 0u64, HashSet::new());
    while let Some(r) = by.get(&(i + 1)) {
        if r.buys.is_empty() { break; }
        i += 1; n += 1; sol += r.buys.iter().map(|b| b.1).sum::<u64>(); sigs.insert(r.sig);
    }
    (n, sol, sigs)
}

#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct Rivals { pub bundle_txs: usize, pub bundle_sol: u64, pub rival_buy_txs_ahead: usize, pub rival_buyers_ahead: usize, pub rival_sol_ahead: u64, pub first_non_bundle: bool }

/// who was ahead of us besides the creator bundle (ok buys strictly between the create and our tx, excluding the bundle)
pub fn rivals(recs: &[ExecRec], create_sig: Option<&[u8; 64]>, our: &[u8; 64], us: &Pk) -> Option<Rivals> {
    let mut v: Vec<&ExecRec> = recs.iter().collect();
    v.sort_by_key(|r| (r.slot, r.index));
    v.dedup_by_key(|r| (r.slot, r.index));
    let c = v.iter().position(|r| r.is_create || create_sig.is_some_and(|s| *s == r.sig))?;
    let o = v.iter().position(|r| r.sig == *our)?;
    let (bn, bsol, bsigs) = bundle_after(recs, v[c]);
    let mut out = Rivals { bundle_txs: bn, bundle_sol: bsol, rival_buy_txs_ahead: 0, rival_buyers_ahead: 0, rival_sol_ahead: 0, first_non_bundle: true };
    let mut who = HashSet::new();
    if o > c {
        for r in &v[c + 1..o] {
            if !r.ok || bsigs.contains(&r.sig) { continue; }
            let theirs: Vec<_> = r.buys.iter().filter(|b| b.0 != *us).collect();
            if theirs.is_empty() { continue; }
            out.rival_buy_txs_ahead += 1;
            for b in theirs { who.insert(b.0); out.rival_sol_ahead += b.1; }
        }
    }
    out.rival_buyers_ahead = who.len();
    out.first_non_bundle = out.rival_buy_txs_ahead == 0;
    Some(out)
}

/// the watchlist's per-creator creator-bundle size (APEX-RECHECK's "bundle_txs_median"; absent = unknown)
pub fn parse_bundle_hints(text: &str) -> HashMap<Pk, f64> {
    let mut m = HashMap::new();
    let Ok(v) = serde_json::from_str::<serde_json::Value>(text.trim()) else { return m };
    let list = match &v { serde_json::Value::Array(a) => a.clone(), serde_json::Value::Object(o) => ["creators", "watchlist", "list"].iter().find_map(|k| o.get(*k).and_then(|x| x.as_array()).cloned()).unwrap_or_default(), _ => vec![] };
    for e in list {
        if let (Some(c), Some(b)) = (e["creator"].as_str().and_then(parse_pk), e["bundle_txs_median"].as_f64()) { m.insert(c, b); }
    }
    m
}

/// how long to wait for the creator bundle after the create: `mode` auto = only for creators whose bundle median is
/// >= 0.5 tx (72% of the watched launches have none: they fire at once), until that many bundle txs are seen or `max_us`;
/// always = every creator up to `max_us` (and the hint's count when known); never = no wait. -> (wait µs, txs to expect)
pub fn bundle_plan(mode: &str, hint: Option<f64>, max_us: u64) -> (u64, Option<usize>) {
    let n = hint.filter(|h| *h >= 0.5).map(|h| h.ceil() as usize);
    match mode {
        "never" => (0, None),
        "always" => (max_us, n),
        _ => if n.is_some() { (max_us, n) } else { (0, None) },
    }
}
