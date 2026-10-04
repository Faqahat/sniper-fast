//! Transfer classification and the other derived fields of exec.jsonl and wallet.jsonl (PLAN WP-08 item 3; MEASUREMENT
//! §4.14 `transfers`, `tip_total`, `tip_asked`, `tip_senders`, `jito_tipped`, `bundle`, `arb_like`; kinds in A.4).
//!
//! [`annotate`] fills them into a §4.14 record from the record's own fields (`keys`, `ixs`, `inner`, `pre` / `post`,
//! `pre_tok` / `post_tok`, `venues`, `pools`), on the recorder's writer thread: `src/rec/exec.rs` calls it for every
//! exec.jsonl line, and the wallet.jsonl writer (WP-03b) makes the same one call, so both streams classify alike
//! whatever produced the record (the transaction stream, a backfilled or a wallet `getTransaction`).
//!
//! - **The tip map** ([`tip_map`]): every sender tip account we know, mapped to its sender: `send::tip_owner_names`, the
//!   names rivals.jsonl's `tips` carry too: the code's lists (`known_tip_accounts`, `OTHER_TIP_ACCOUNTS`), then
//!   `data/sender-tip-accounts.json` (compiled in; a service's `sender` field, else its key) for every account those do
//!   not name. Each address WP-08 added to that file carries the provider source it was fetched from
//!   (`tip_account_sources`).
//! - **Kinds**, one per transfer, the first rule that matches:
//!   - System transfers (Transfer, TransferWithSeed, WithdrawNonceAccount): to a tip account: `sender_tip` at the top
//!     level, `cpi_tip` from inside a program (stack height > 1); funding an account inside an Associated Token Account
//!     instruction: `rent_create`; into the signer's WSOL account with a SyncNative of that account after it: `wrap`;
//!     to a platform wallet (`data/platform-fee-wallets.json`) or an account it owns: `platform_fee`; between the signer
//!     and accounts it owns: `self`; else `other`. CreateAccount (with or without seed): `rent_create`.
//!   - SPL Token / Token-2022 transfers (Transfer, TransferChecked): inside a PumpSwap buy or sell to its protocol fee
//!     token account, coin-creator vault token account or buyback token account (the layout build.rs fills: accounts
//!     10, 17 and the last): `venue_fee`; to a platform wallet's token account: `platform_fee`; between token accounts
//!     the signer owns: `self`; else `other` (swap legs, transfers to pools).
//!   - CloseAccount: of the signer's WSOL account: `unwrap`; of any other token account: `rent_close`. Its lamports are
//!     the account's balance when it closes: the pre-balance plus what the instructions before it moved in or out
//!     (System transfers and creations, WSOL token transfers).
//!   - A failed transaction moved nothing: its transfers are the ones its instructions asked for (and the inner ones
//!     the provider recorded before the error; they name the lane it used); `ok` false says so, its `tip_total` is 0
//!     (`tip_asked` keeps the asked tips) and its `bundle` null.
//!   - `depth` is 0 at the top level, else the stack height minus 1 (1 when the provider gives no height); `ix` is the
//!     top-level instruction. `sender` names the tip service (or the platform of a `platform_fee`).
//! - **Bundle membership** (`bundle`): ours from the block engine's `processed` results ([`note_bundle_processed`],
//!   `src` `jito-result`, `known` true); any other successful transaction that tips a Jito tip account is marked
//!   `heuristic` (`known` false: a Jito tip makes it a bundle candidate); a failed one is in no bundle (a bundle lands only
//!   when all of it succeeds). Block adjacency and the explorer lookup (`explorer`) refine these offline (WP-10): a record
//!   is written once, before its neighbours in the block are all known.
//! - **arb_like** (`{is, why}`): the test of `engine.rs::record_rival`: two venue programs other than the aggregator
//!   (`venues`), two watched pools (`pools`), a signer seen doing that before (`known`); plus `program`: a watched pool
//!   touched by a top-level program seen at the top of an arbitrage-like transaction before. The learned sets are
//!   process-wide and bounded, like the engine's.
use crate::tx::{b58, Pk};
use base64::Engine as _;
use rustc_hash::{FxHashMap, FxHashSet};
use serde_json::{json, Value};
use std::sync::{Arc, LazyLock, Mutex};

const SYSTEM: Pk = [0u8; 32];
static MEMO: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"));
const B64: base64::engine::GeneralPurpose = base64::engine::general_purpose::STANDARD;

/// The transfer kinds (MEASUREMENT A.4)
pub mod kind {
    pub const SENDER_TIP: &str = "sender_tip";
    pub const CPI_TIP: &str = "cpi_tip";
    pub const WRAP: &str = "wrap";
    pub const UNWRAP: &str = "unwrap";
    pub const SELF: &str = "self";
    pub const VENUE_FEE: &str = "venue_fee";
    pub const PLATFORM_FEE: &str = "platform_fee";
    pub const RENT_CREATE: &str = "rent_create";
    pub const RENT_CLOSE: &str = "rent_close";
    pub const OTHER: &str = "other";
    pub const ALL: [&str; 10] = [SENDER_TIP, CPI_TIP, WRAP, UNWRAP, SELF, VENUE_FEE, PLATFORM_FEE, RENT_CREATE, RENT_CLOSE, OTHER];
}

fn decode_pk(s: &str) -> Option<Pk> { bs58::decode(s).into_vec().ok().and_then(|v| Pk::try_from(v).ok()) }

// ------------------------------------------------------------------------------------------------ the tip map

/// Every known sender tip account and its sender's name (see the module docs for the order of the sources)
pub struct TipMap {
    map: FxHashMap<Pk, Arc<str>>,
    /// Jito's eight tip accounts (`jito_tipped`)
    jito: FxHashSet<Pk>,
}

impl TipMap {
    /// The map from the code's lists plus the catalogue `json` (the `data/sender-tip-accounts.json` layout: `{service:
    /// {"sender"?, "tip_accounts": [..]}}`, [`crate::send::add_tip_catalogue`]): an account already named keeps its first
    /// name, a service without a `sender` field is named by its key
    pub fn build(json: &str) -> TipMap {
        let mut names = crate::send::code_tip_names();
        crate::send::add_tip_catalogue(&mut names, json);
        TipMap::from_names(names)
    }
    /// The map of account -> sender `names` (Jito's eight accounts known from the code)
    pub fn from_names(names: FxHashMap<Pk, String>) -> TipMap {
        let map = names.into_iter().map(|(k, n)| (k, Arc::from(n.as_str()))).collect();
        let jito = crate::send::known_tip_accounts(crate::config::SendKind::JitoBundle).iter().filter_map(|a| decode_pk(a)).collect();
        TipMap { map, jito }
    }
    /// the sender a tip to `k` pays
    pub fn get(&self, k: &Pk) -> Option<&str> { self.map.get(k).map(|s| &**s) }
    pub fn is_jito(&self, k: &Pk) -> bool { self.jito.contains(k) }
    pub fn len(&self) -> usize { self.map.len() }
    pub fn is_empty(&self) -> bool { self.map.is_empty() }
    /// account -> sender
    pub fn names(&self) -> FxHashMap<Pk, String> { self.map.iter().map(|(k, v)| (*k, v.to_string())).collect() }
}

/// The run's tip map: `send::tip_owner_names()`, the same names rivals.jsonl's `tips` carry (the code's lists, then the
/// compiled-in catalogue `data/sender-tip-accounts.json`)
pub fn tip_map() -> &'static TipMap {
    static M: LazyLock<TipMap> = LazyLock::new(|| TipMap::from_names(crate::send::tip_owner_names()));
    &M
}

/// Wallets that collect platform (trading terminal, bot) fees, by platform: `data/platform-fee-wallets.json`
/// (`{"platforms": {name: {"wallets": [{"address", "source_url", "fetched", "attribution"}]}}}`; compiled in)
pub struct PlatformMap { map: FxHashMap<Pk, Arc<str>> }

impl PlatformMap {
    pub fn build(json: &str) -> PlatformMap {
        let mut map = FxHashMap::default();
        let v: Value = serde_json::from_str(json).unwrap_or(Value::Null);
        for (name, p) in v["platforms"].as_object().into_iter().flatten() {
            let name: Arc<str> = Arc::from(name.as_str());
            for w in p["wallets"].as_array().into_iter().flatten() {
                if let Some(k) = w["address"].as_str().and_then(decode_pk) { map.entry(k).or_insert_with(|| name.clone()); }
            }
        }
        PlatformMap { map }
    }
    pub fn get(&self, k: &Pk) -> Option<&str> { self.map.get(k).map(|s| &**s) }
    pub fn len(&self) -> usize { self.map.len() }
    pub fn is_empty(&self) -> bool { self.map.is_empty() }
}

pub fn platform_map() -> &'static PlatformMap {
    static M: LazyLock<PlatformMap> = LazyLock::new(|| PlatformMap::build(include_str!("../data/platform-fee-wallets.json")));
    &M
}

// ------------------------------------------------------------------------------------------------ the record's view

/// One instruction: its program's index, its accounts' indexes (into the full key list), its data and stack height
#[derive(Clone, Debug)]
struct Ixn { prog: usize, accts: Vec<usize>, data: Vec<u8>, height: Option<u32> }

/// A token account's mint and owner, when the token balances or an initialising instruction say
#[derive(Clone, Copy, Debug, Default)]
struct TokInfo { mint: Option<Pk>, owner: Option<Pk> }

/// What classification reads from a §4.14 record
struct View {
    keys: Vec<Pk>,
    signer: Option<Pk>,
    top: Vec<Ixn>,
    /// inner instructions per top-level index; None when the provider omitted them
    inner: Option<Vec<Vec<Ixn>>>,
    pre: Vec<u64>,
    tok: FxHashMap<usize, TokInfo>,
}

impl View {
    /// The view of an exec.jsonl / wallet.jsonl record; None if its keys or instructions do not decode
    fn from_json(v: &Value) -> Option<View> {
        let keys: Vec<Pk> = v["keys"].as_array()?.iter().map(|k| k.as_str().and_then(decode_pk)).collect::<Option<_>>()?;
        let idx = |x: &Value| -> Option<Vec<usize>> { x.as_array()?.iter().map(|i| i.as_u64().map(|i| i as usize)).collect() };
        let ixn = |x: &Value, height: Option<u32>| -> Option<Ixn> {
            Some(Ixn { prog: x["p"].as_u64()? as usize, accts: idx(&x["a"])?, data: B64.decode(x["d"].as_str()?).ok()?, height })
        };
        let top: Vec<Ixn> = v["ixs"].as_array()?.iter().map(|x| ixn(x, Some(1))).collect::<Option<_>>()?;
        let inner = match v["inner"].as_array() {
            None => None,
            Some(groups) => {
                let mut per = vec![Vec::new(); top.len()];
                for g in groups {
                    let i = g["ix"].as_u64()? as usize;
                    let list: Vec<Ixn> = g["list"].as_array()?.iter().map(|x| ixn(x, x["h"].as_u64().map(|h| h as u32))).collect::<Option<_>>()?;
                    if let Some(slot) = per.get_mut(i) { slot.extend(list); }
                }
                Some(per)
            }
        };
        let pre: Vec<u64> = v["pre"].as_array().map(|a| a.iter().filter_map(Value::as_u64).collect()).unwrap_or_default();
        let mut tok: FxHashMap<usize, TokInfo> = FxHashMap::default();
        for side in ["pre_tok", "post_tok"] {
            for b in v[side].as_array().into_iter().flatten() {
                let Some(i) = b["i"].as_u64() else { continue };
                let e = tok.entry(i as usize).or_default();
                if let Some(m) = b["mint"].as_str().and_then(decode_pk) { e.mint = Some(m); }
                if let Some(o) = b["owner"].as_str().filter(|o| !o.is_empty()).and_then(decode_pk) { e.owner = Some(o); }
            }
        }
        Some(View { signer: keys.first().copied(), keys, top, inner, pre, tok })
    }
}

// ------------------------------------------------------------------------------------------------ classification

/// One classified transfer (`transfers[]`)
#[derive(Clone, Debug, PartialEq)]
pub struct Transfer {
    pub kind: &'static str,
    pub from: Pk,
    pub to: Pk,
    /// lamports moved (System transfers and creations, closes); None for token transfers, or a close whose balance is
    /// not known
    pub lamports: Option<u64>,
    pub mint: Option<Pk>,
    /// raw token amount (token transfers)
    pub amount: Option<u64>,
    /// the tip service (tips), the platform (platform fees)
    pub sender: Option<String>,
    pub depth: u32,
    pub ix: u32,
}

impl Transfer {
    pub fn json(&self) -> Value {
        json!({ "kind": self.kind, "from": b58(&self.from), "to": b58(&self.to), "lamports": self.lamports, "mint": self.mint.as_ref().map(b58),
            "amount": self.amount.map(|a| a.to_string()), "sender": self.sender, "depth": self.depth, "ix": self.ix })
    }
}

/// A record's transfers and tip summary
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Classified {
    pub transfers: Vec<Transfer>,
    /// sender_tip + cpi_tip lamports the instructions ask for (paid only when the transaction succeeded: the record's
    /// `tip_asked`; its `tip_total` is this when `ok`, else 0)
    pub tip_asked: u64,
    /// the tip services, in the order first tipped
    pub tip_senders: Vec<String>,
    /// tips a Jito tip account
    pub jito_tipped: bool,
}

/// the PumpSwap fee token accounts of a buy / sell (MEASUREMENT §4.14 `venue_fee`): protocol fee recipient's token
/// account (10), coin-creator vault token account (17), the buyback token account (the last; build.rs `pump_leg`)
fn pump_fee_accounts(accts: &[usize]) -> Vec<usize> {
    if accts.len() < 19 { return vec![]; }
    let mut v = vec![accts[10], accts[17]];
    let last = accts[accts.len() - 1];
    if accts.len() > 21 && !accts[..19].contains(&last) { v.push(last); }
    v
}

fn u64_at(d: &[u8], at: usize) -> Option<u64> { d.get(at..at + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap())) }
fn pk_at(d: &[u8], at: usize) -> Option<Pk> { d.get(at..at + 32).map(|b| b.try_into().unwrap()) }

/// what one instruction does to lamports and tokens, as far as classification cares
enum Op {
    /// System Transfer / TransferWithSeed / WithdrawNonceAccount
    Lamports { from: usize, to: usize, lamports: u64 },
    /// System CreateAccount / CreateAccountWithSeed
    Create { from: usize, to: usize, lamports: u64 },
    /// SPL Token / Token-2022 Transfer, TransferChecked (`mint`: TransferChecked's mint account)
    Token { from: usize, to: usize, amount: u64, mint: Option<usize> },
    Close { acct: usize, to: usize },
    Sync { acct: usize },
    /// InitializeAccount{,2,3}: the account's mint and owner
    Init { acct: usize, mint: usize, owner: Option<Pk>, owner_idx: Option<usize> },
    /// Associated Token Account Create / CreateIdempotent: (ata, wallet, mint)
    AtaCreate { ata: usize, wallet: usize, mint: usize },
    None,
}

fn decode(keys: &[Pk], x: &Ixn) -> Op {
    let Some(prog) = keys.get(x.prog) else { return Op::None };
    let a = |i: usize| x.accts.get(i).copied().filter(|k| *k < keys.len());
    let d = &x.data;
    if *prog == SYSTEM {
        let Some(tag) = d.get(..4).map(|b| u32::from_le_bytes(b.try_into().unwrap())) else { return Op::None };
        return match tag {
            0 => match (a(0), a(1), u64_at(d, 4)) { (Some(from), Some(to), Some(lamports)) => Op::Create { from, to, lamports }, _ => Op::None },
            2 => match (a(0), a(1), u64_at(d, 4)) { (Some(from), Some(to), Some(lamports)) => Op::Lamports { from, to, lamports }, _ => Op::None },
            3 => {
                // CreateAccountWithSeed: base (32), seed (u64 length + bytes), lamports, space, owner
                let len = u64_at(d, 36).unwrap_or(u64::MAX) as usize;
                match (a(0), a(1), 44usize.checked_add(len).and_then(|o| u64_at(d, o))) {
                    (Some(from), Some(to), Some(lamports)) => Op::Create { from, to, lamports }, _ => Op::None }
            }
            5 => match (a(0), a(1), u64_at(d, 4)) { (Some(from), Some(to), Some(lamports)) => Op::Lamports { from, to, lamports }, _ => Op::None },
            11 => match (a(0), a(2), u64_at(d, 4)) { (Some(from), Some(to), Some(lamports)) => Op::Lamports { from, to, lamports }, _ => Op::None },
            _ => Op::None,
        };
    }
    if *prog == *crate::pda::TOKEN_PROGRAM || *prog == *crate::pda::TOKEN_2022 {
        return match d.first() {
            Some(3) => match (a(0), a(1), u64_at(d, 1)) { (Some(from), Some(to), Some(amount)) => Op::Token { from, to, amount, mint: None }, _ => Op::None },
            Some(12) => match (a(0), a(2), u64_at(d, 1)) { (Some(from), Some(to), Some(amount)) => Op::Token { from, to, amount, mint: a(1) }, _ => Op::None },
            Some(9) => match (a(0), a(1)) { (Some(acct), Some(to)) => Op::Close { acct, to }, _ => Op::None },
            Some(17) => a(0).map_or(Op::None, |acct| Op::Sync { acct }),
            Some(1) => match (a(0), a(1), a(2)) { (Some(acct), Some(mint), Some(o)) => Op::Init { acct, mint, owner: None, owner_idx: Some(o) }, _ => Op::None },
            Some(16) | Some(18) => match (a(0), a(1), pk_at(d, 1)) { (Some(acct), Some(mint), Some(owner)) => Op::Init { acct, mint, owner: Some(owner), owner_idx: None }, _ => Op::None },
            _ => Op::None,
        };
    }
    if *prog == *crate::pda::ATA_PROGRAM {
        return match (d.first().copied().unwrap_or(0), a(1), a(2), a(3)) {
            (0 | 1, Some(ata), Some(wallet), Some(mint)) => Op::AtaCreate { ata, wallet, mint },
            _ => Op::None,
        };
    }
    Op::None
}

/// Classify a view's transfers (the module docs give the rules)
fn classify_view(v: &View, tips: &TipMap, platforms: &PlatformMap) -> Classified {
    let keys = &v.keys;
    let signer = v.signer;
    let wsol = *crate::venues::WSOL;
    let mut tok = v.tok.clone();
    // the running lamport balance of every account, from the pre-balances (the closes' lamports)
    let mut bal: Option<Vec<i128>> = (v.pre.len() == keys.len()).then(|| v.pre.iter().map(|x| *x as i128).collect());
    let mut out: Vec<Transfer> = Vec::new();
    // wrap candidates (transfer index, account, sequence number) and every SyncNative (sequence number, account)
    let mut wrap_cand: Vec<(usize, usize, usize)> = Vec::new();
    let mut syncs: Vec<(usize, usize)> = Vec::new();
    let mut seq = 0usize;
    let empty: Vec<Ixn> = Vec::new();
    let owner_of = |tok: &FxHashMap<usize, TokInfo>, k: usize| tok.get(&k).and_then(|t| t.owner);
    let mine = |tok: &FxHashMap<usize, TokInfo>, k: usize| signer.is_some() && (Some(keys[k]) == signer || owner_of(tok, k) == signer);
    let platform = |tok: &FxHashMap<usize, TokInfo>, k: usize| -> Option<String> {
        platforms.get(&keys[k]).or_else(|| owner_of(tok, k).and_then(|o| platforms.get(&o))).map(str::to_string)
    };
    for (i, top) in v.top.iter().enumerate() {
        let inner = v.inner.as_ref().and_then(|x| x.get(i)).unwrap_or(&empty);
        // the invocation stack by height: (program index, the PumpSwap fee accounts when it is a PumpSwap swap)
        let mut stack: Vec<(usize, Vec<usize>)> = Vec::new();
        for (n, x) in std::iter::once(top).chain(inner.iter()).enumerate() {
            seq += 1;
            let h = if n == 0 { 1 } else { x.height.unwrap_or(2).max(2) as usize };
            stack.truncate(h - 1);
            let parent = stack.last().cloned();
            let fees = if keys.get(x.prog) == Some(&*crate::venues::PUMPSWAP) { pump_fee_accounts(&x.accts) } else { vec![] };
            stack.push((x.prog, fees));
            let depth = (h - 1) as u32;
            let parent_prog = parent.as_ref().and_then(|p| keys.get(p.0));
            let t = |kind: &'static str, from: usize, to: usize, lamports: Option<u64>, mint: Option<Pk>, amount: Option<u64>, sender: Option<String>| {
                Transfer { kind, from: keys[from], to: keys[to], lamports, mint, amount, sender, depth, ix: i as u32 }
            };
            match decode(keys, x) {
                Op::Lamports { from, to, lamports } => {
                    if let Some(b) = bal.as_mut() { b[from] -= lamports as i128; b[to] += lamports as i128; }
                    let x = if let Some(name) = tips.get(&keys[to]) {
                        t(if depth == 0 { kind::SENDER_TIP } else { kind::CPI_TIP }, from, to, Some(lamports), None, None, Some(name.to_string()))
                    } else if parent_prog == Some(&*crate::pda::ATA_PROGRAM) {
                        t(kind::RENT_CREATE, from, to, Some(lamports), None, None, None)
                    } else if tok.get(&to).is_some_and(|i| i.mint == Some(wsol)) && signer.is_some() && owner_of(&tok, to) == signer && mine(&tok, from) {
                        // `self` unless a SyncNative of the account follows (then `wrap`, below); a third party paying
                        // into the signer's WSOL account is neither (review WP-08 #19)
                        wrap_cand.push((out.len(), to, seq));
                        t(kind::SELF, from, to, Some(lamports), None, None, None)
                    } else if let Some(p) = platform(&tok, to) {
                        t(kind::PLATFORM_FEE, from, to, Some(lamports), None, None, Some(p))
                    } else if mine(&tok, from) && mine(&tok, to) {
                        t(kind::SELF, from, to, Some(lamports), None, None, None)
                    } else {
                        t(kind::OTHER, from, to, Some(lamports), None, None, None)
                    };
                    out.push(x);
                }
                Op::Create { from, to, lamports } => {
                    if let Some(b) = bal.as_mut() { b[from] -= lamports as i128; b[to] += lamports as i128; }
                    out.push(t(kind::RENT_CREATE, from, to, Some(lamports), None, None, None));
                }
                Op::Token { from, to, amount, mint } => {
                    let m = mint.map(|k| keys[k]).or_else(|| tok.get(&from).and_then(|i| i.mint)).or_else(|| tok.get(&to).and_then(|i| i.mint));
                    // a WSOL token transfer moves lamports too
                    if m == Some(wsol) { if let Some(b) = bal.as_mut() { b[from] -= amount as i128; b[to] += amount as i128; } }
                    let (k, sender) = if parent.as_ref().is_some_and(|p| p.1.contains(&to)) { (kind::VENUE_FEE, None) }
                        else if let Some(p) = platform(&tok, to) { (kind::PLATFORM_FEE, Some(p)) }
                        else if signer.is_some() && owner_of(&tok, from) == signer && owner_of(&tok, to) == signer { (kind::SELF, None) }
                        else { (kind::OTHER, None) };
                    out.push(t(k, from, to, None, m, Some(amount), sender));
                }
                Op::Close { acct, to } => {
                    let lamports = match bal.as_mut() {
                        Some(b) => { let l = b[acct].max(0); b[to] += l; b[acct] = 0; u64::try_from(l).ok() }
                        None => None,
                    };
                    let info = tok.get(&acct).copied().unwrap_or_default();
                    let k = if info.mint == Some(wsol) && signer.is_some() && info.owner == signer { kind::UNWRAP } else { kind::RENT_CLOSE };
                    out.push(t(k, acct, to, lamports, info.mint, None, None));
                }
                Op::Sync { acct } => syncs.push((seq, acct)),
                Op::Init { acct, mint, owner, owner_idx } => {
                    let e = tok.entry(acct).or_default();
                    e.mint = Some(keys[mint]);
                    if let Some(o) = owner.or_else(|| owner_idx.map(|k| keys[k])) { e.owner = Some(o); }
                }
                Op::AtaCreate { ata, wallet, mint } => {
                    let e = tok.entry(ata).or_default();
                    e.mint = Some(keys[mint]);
                    e.owner = Some(keys[wallet]);
                }
                Op::None => {}
            }
        }
    }
    // a transfer into the signer's WSOL account is a wrap when a SyncNative of that account follows it
    for (n, acct, s) in wrap_cand {
        if syncs.iter().any(|(q, a)| *a == acct && *q > s) { out[n].kind = kind::WRAP; }
    }
    let mut c = Classified { transfers: out, ..Default::default() };
    for t in c.transfers.iter().filter(|t| t.kind == kind::SENDER_TIP || t.kind == kind::CPI_TIP) {
        c.tip_asked += t.lamports.unwrap_or(0);
        if let Some(s) = &t.sender { if !c.tip_senders.contains(s) { c.tip_senders.push(s.clone()); } }
        if tips.is_jito(&t.to) { c.jito_tipped = true; }
    }
    c
}

/// Classify the transfers of a §4.14 record (exec.jsonl, wallet.jsonl) with the run's maps; None if its keys or
/// instructions do not decode
pub fn classify(v: &Value) -> Option<Classified> { View::from_json(v).map(|view| classify_view(&view, tip_map(), platform_map())) }

/// The same with given maps (tests, offline tools)
pub fn classify_with(v: &Value, tips: &TipMap, platforms: &PlatformMap) -> Option<Classified> { View::from_json(v).map(|view| classify_view(&view, tips, platforms)) }

// ------------------------------------------------------------------------------------------------ bundles

/// Our bundles' `processed` results by our transaction's signature: (bundle id, slot, bundle index). Bounded
#[derive(Default)]
struct Ours { map: FxHashMap<String, (String, u64, u64)>, order: std::collections::VecDeque<String> }
static OURS: LazyLock<Mutex<Ours>> = LazyLock::new(Default::default);
const OURS_MAX: usize = 20_000;

/// A `processed` result of one of our bundles (send/jito.rs `on_result`, where the bundle's transaction is known: WP-05
/// makes this call), so that its exec.jsonl / wallet.jsonl line names the bundle (`bundle.src` `jito-result`)
pub fn note_bundle_processed(sig: &str, bundle: &str, slot: u64, index: u64) {
    let mut g = OURS.lock().unwrap_or_else(|e| e.into_inner());
    if g.map.insert(sig.to_string(), (bundle.to_string(), slot, index)).is_none() { g.order.push_back(sig.to_string()); }
    while g.order.len() > OURS_MAX { if let Some(o) = g.order.pop_front() { g.map.remove(&o); } }
}

/// `bundle` (MEASUREMENT §4.14): ours from the results, else a heuristic mark on a Jito-tipped transaction, else null.
/// Stage 0 sends one-transaction bundles (position 0, size 1). A failed transaction is in no bundle: a Jito bundle
/// lands only when all its transactions succeed (review WP-08 #5)
fn bundle_json(sig: Option<&str>, ok: bool, jito_tipped: bool) -> Value {
    if !ok { return Value::Null; }
    if let Some((id, slot, index)) = sig.and_then(|s| OURS.lock().unwrap_or_else(|e| e.into_inner()).map.get(s).cloned()) {
        return json!({ "known": true, "src": "jito-result", "id": id, "pos": 0, "size": 1, "slot": slot, "index": index });
    }
    if jito_tipped { return json!({ "known": false, "src": "heuristic", "id": null, "pos": null, "size": null }); }
    Value::Null
}

// ------------------------------------------------------------------------------------------------ arb_like

/// Signers and top-level programs seen in arbitrage-like transactions (process-wide, bounded like the engine's set)
#[derive(Default)]
struct Learned { signers: FxHashSet<Pk>, programs: FxHashSet<Pk> }
static LEARNED: LazyLock<Mutex<Learned>> = LazyLock::new(Default::default);
const LEARNED_MAX: usize = 200_000;

/// programs that never make a transaction an arbitrage: builtins and the venues themselves
fn plain_program(k: &Pk) -> bool {
    static VENUES: LazyLock<FxHashSet<Pk>> = LazyLock::new(|| crate::engine::amm_programs().into_keys().collect());
    *k == SYSTEM || *k == crate::tx::COMPUTE_BUDGET || *k == *crate::pda::TOKEN_PROGRAM || *k == *crate::pda::TOKEN_2022 || *k == *crate::pda::ATA_PROGRAM
        || *k == *MEMO || VENUES.contains(k)
}

/// `arb_like` of a record: `{is, why}` (module docs)
fn arb_like(v: &Value, view: &View) -> Value {
    let venues: Vec<&str> = v["venues"].as_array().into_iter().flatten().filter_map(Value::as_str).collect();
    let agg = venues.contains(&"jupiter");
    let n_venues = venues.len() - agg as usize;
    let pools = v["pools"].as_array().map_or(0, |p| p.len());
    let tops: Vec<Pk> = view.top.iter().filter_map(|x| view.keys.get(x.prog).copied()).filter(|k| !plain_program(k)).collect();
    let mut g = LEARNED.lock().unwrap_or_else(|e| e.into_inner());
    let why = if n_venues >= 2 { Some("venues") } else if pools >= 2 { Some("pools") }
        else if view.signer.is_some_and(|s| g.signers.contains(&s)) { Some("known") }
        else if pools >= 1 && tops.iter().any(|p| g.programs.contains(p)) { Some("program") }
        else { None };
    if matches!(why, Some("venues") | Some("pools")) && !agg {
        if let Some(s) = view.signer { if g.signers.len() < LEARNED_MAX { g.signers.insert(s); } }
        for p in tops { if g.programs.len() < LEARNED_MAX { g.programs.insert(p); } }
    }
    json!({ "is": why.is_some(), "why": why })
}

// ------------------------------------------------------------------------------------------------ the hook

/// Fill the derived fields of a §4.14 record in place: `transfers`, `tip_total`, `tip_asked`, `tip_senders`,
/// `jito_tipped`, `bundle`, `arb_like`. Runs on the recorder's writer thread (src/rec/exec.rs for exec.jsonl; the
/// wallet.jsonl writer makes the same call). A record whose keys or instructions do not decode keeps them null. A failed
/// transaction (`ok` false) keeps the transfers it asked for (they name its lane) but paid no tip (`tip_total` 0,
/// `tip_asked` the asked lamports) and was in no bundle (review WP-08 #5)
pub fn annotate(v: &mut Value) {
    let Some(view) = View::from_json(v) else { return };
    let c = classify_view(&view, tip_map(), platform_map());
    let arb = arb_like(v, &view);
    let ok = v["ok"].as_bool() != Some(false);
    let bundle = bundle_json(v["sig"].as_str(), ok, c.jito_tipped);
    v["transfers"] = Value::Array(c.transfers.iter().map(Transfer::json).collect());
    v["tip_total"] = json!(if ok { c.tip_asked } else { 0 });
    v["tip_asked"] = json!(c.tip_asked);
    v["tip_senders"] = json!(c.tip_senders);
    v["jito_tipped"] = json!(c.jito_tipped);
    v["bundle"] = bundle;
    v["arb_like"] = arb;
}

#[cfg(test)]
mod tests;
