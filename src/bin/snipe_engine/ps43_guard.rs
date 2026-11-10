// =====================================================================================================================
// dip43 C2 (Builder C): the snipe-guard program on the pre-send tries (program/snipe-guard; ops/guard/DEPLOY.md). DEFAULT OFF:
// with `--presend-live-guard off` (the default) nothing here runs and every try is dip42's byte for byte (the Lighthouse slot
// deadline at index 2; test `dip43_guard_off_is_dip42_bytes`).
//   deadline  the guard REPLACES the Lighthouse instruction with the same slot deadline only (landing A/B: --presend-live-guard-ab on
//             = odd windows snipe-guard, even windows Lighthouse);
//   holders   deadline + holder floors (onchain G-A): the top N holders by TRUE balance at signing (ours excluded, >= MINPCT % of
//             supply), floor = THETA x balance, abort when MORE THAN MAXLEAVERS are below (6:0.9:1:1.0 = abort at 2 or more). The
//             holders' token accounts are their Token-2022 ATAs, derived locally (cached). A missing or stale (> --presend-live-guard-
//             max-age-ms) true-balance snapshot signs the deadline only (`guard.reason` "no_snapshot" / "stale"): never a wait.
// The program id comes ONLY from --presend-live-guard-program (no id in the code). A wallet not compiled into the program needs
// --presend-live-guard-allowlist <PDA>. At start (fail closed): the program account is executable and a passing and an aborting
// try simulate with the expected decoded codes. Every guarded try's failure at the guard is decoded from the opaque custom code
// (snipe_guard::client::decode) into `guard_abort {kind, idx, cnt, gap, ...}` on presend_attempt_land; result "deadline" for a
// late try (as Lighthouse's), "guard_abort" for any other kind, "guard_other" for a non-custom failure at the guard.
// =====================================================================================================================
use super::*;
use snipe_guard::client as sgc;
use snipe_guard::logic as sgl;

/// the flags (all refused unless --presend-live-guard is deadline | holders; known to the start-up flag check through pslive's G43FLAGS)
pub const FLAG_MODE: &str = "--presend-live-guard";
pub const FLAG_PROGRAM: &str = "--presend-live-guard-program";
pub const FLAG_HOLDERS: &str = "--presend-live-guard-holders";
pub const FLAG_AB: &str = "--presend-live-guard-ab";
pub const FLAG_ALLOWLIST: &str = "--presend-live-guard-allowlist";
pub const FLAG_MAX_AGE: &str = "--presend-live-guard-max-age-ms";
/// dip43d (owner 11-11 "Build, hot switch"; bait79 + band42 studies): the CURVE band. D in (0, 1): a try aborts at execution when the curve's
/// token account holds more than the balance at which the price is D under the try's signing price (price ∝ 1/vtok²). With the band live EVERY
/// window carries snipe-guard (the A/B's Lighthouse arm: deadline + band, no floors). Hot switch: control key "curve_deep" live | log.
pub const FLAG_CURVE: &str = "--presend-live-guard-curve-deep";
/// a pump curve's token account holds its virtual token reserve minus 73,000,000 whole tokens (1e9 supply; 206.9M unsellable + the 279.9M
/// virtual offset; verified on chain 11-11 on two live tokens: vtok − ata = 73,000,000,000,000 raw)
pub const PUMP_ATA_OFFSET: u64 = 73_000_000_000_000;
/// the band's upper bound on the curve token account for a try signed at `vtok`: the account above it = the price more than `d` under the signing price
pub fn curve_hi(vtok: u64, d: f64) -> u64 { (((vtok as f64) / (1.0 - d).sqrt()).floor().max(0.0) as u64).saturating_sub(PUMP_ATA_OFFSET) }

/// signatures of Lighthouse-arm tries that carried snipe-guard (band live): their guard failures are decoded too (bounded)
static SG_L: std::sync::Mutex<Option<FxHashSet<[u8; 64]>>> = std::sync::Mutex::new(None);
pub fn sg_l_note(sig: &[u8; 64]) { let mut g = SG_L.lock().unwrap(); let s = g.get_or_insert_with(FxHashSet::default); if s.len() > 200_000 { s.clear(); } s.insert(*sig); }
pub fn sg_l_has(sig: &[u8; 64]) -> bool { SG_L.lock().unwrap().as_ref().is_some_and(|s| s.contains(sig)) }

/// the most holder floors one try carries (a 1,232-byte try fits about 8 next to the buy; the builder drops from the tail)
pub const MAXN: usize = 10;
/// pump tokens: 1e9 whole tokens of 6 decimals
const SUPPLY: f64 = 1e15;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode { Deadline, Holders }

/// the guard's configuration (None in Cfg = off, the default)
#[derive(Clone, Debug, PartialEq)]
pub struct G43 {
    pub mode: Mode,
    pub program: Pk,
    /// N holders, floor THETA x balance, abort when MORE THAN `max_leavers` are below, holders >= `min_pct` % of supply
    pub n: usize,
    pub theta: f64,
    pub max_leavers: u8,
    pub min_pct: f64,
    /// window parity A/B: odd windows the guard, even windows Lighthouse
    pub ab: bool,
    pub allowlist: Option<Pk>,
    /// a true-balance snapshot older than this signs the deadline only
    pub max_age_ms: u64,
    /// dip43d: the CURVE band's D (None = off)
    pub curve_deep: Option<f64>,
}

fn pk_parse(f: &str, s: &str) -> Result<Pk> {
    let v = bs58::decode(s.trim()).into_vec().map_err(|_| anyhow::anyhow!("{f} {s}: not a base58 public key"))?;
    <[u8; 32]>::try_from(v).map_err(|_| anyhow::anyhow!("{f} {s}: not a 32-byte public key"))
}

/// N:THETA:MAXLEAVERS:MINPCT
pub fn holders_parse(s: &str) -> Result<(usize, f64, u8, f64)> {
    let bad = || anyhow::anyhow!("{FLAG_HOLDERS} {s}: N:THETA:MAXLEAVERS:MINPCT (default 6:0.9:1:1.0 = top 6 holders >= 1% of supply, floor 90%, abort when MORE THAN 1 is below)");
    let v: Vec<&str> = s.split(':').collect();
    if v.len() != 4 { return Err(bad()); }
    let n: usize = v[0].trim().parse().map_err(|_| bad())?;
    let theta: f64 = v[1].trim().parse().map_err(|_| bad())?;
    let ml: u8 = v[2].trim().parse().map_err(|_| bad())?;
    let mp: f64 = v[3].trim().parse().map_err(|_| bad())?;
    if !(1..=MAXN).contains(&n) { bail!("{FLAG_HOLDERS}: N must be 1..{MAXN}"); }
    if !(theta > 0.0 && theta <= 1.0) { bail!("{FLAG_HOLDERS}: THETA must be in (0, 1]"); }
    if ml as usize >= n { bail!("{FLAG_HOLDERS}: MAXLEAVERS must be < N (else the check can never fail)"); }
    if !(mp.is_finite() && (0.0..=100.0).contains(&mp)) { bail!("{FLAG_HOLDERS}: MINPCT must be 0..100 (% of supply)"); }
    Ok((n, theta, ml, mp))
}

impl G43 {
    /// the flags (None = off). `has` / `arg` as Cfg::from_argv's
    pub fn from_flags(has: &dyn Fn(&str) -> bool, arg: &dyn Fn(&str) -> Option<String>) -> Result<Option<G43>> {
        for f in [FLAG_MODE, FLAG_PROGRAM, FLAG_HOLDERS, FLAG_AB, FLAG_ALLOWLIST, FLAG_MAX_AGE, FLAG_CURVE] {
            if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); }
        }
        let mode = match arg(FLAG_MODE).as_deref() {
            None | Some("off") => {
                if let Some(f) = [FLAG_PROGRAM, FLAG_HOLDERS, FLAG_AB, FLAG_ALLOWLIST, FLAG_MAX_AGE, FLAG_CURVE].iter().find(|f| has(f)) { bail!("{f} needs {FLAG_MODE} deadline | holders"); }
                return Ok(None);
            }
            Some("deadline") => Mode::Deadline,
            Some("holders") => Mode::Holders,
            Some(x) => bail!("{FLAG_MODE} {x}: off | deadline | holders"),
        };
        let program = pk_parse(FLAG_PROGRAM, &arg(FLAG_PROGRAM).with_context(|| format!("{FLAG_MODE} {} needs {FLAG_PROGRAM} <PUBKEY> (the id the deploy printed)",
            if mode == Mode::Deadline { "deadline" } else { "holders" }))?)?;
        if program == [0u8; 32] { bail!("{FLAG_PROGRAM}: the system program is not the guard"); }
        let (n, theta, max_leavers, min_pct) = holders_parse(&arg(FLAG_HOLDERS).unwrap_or_else(|| "6:0.9:1:1.0".into()))?;
        if has(FLAG_HOLDERS) && mode != Mode::Holders { bail!("{FLAG_HOLDERS} needs {FLAG_MODE} holders"); }
        let ab = match arg(FLAG_AB).as_deref() { None | Some("off") => false, Some("on") => true, Some(x) => bail!("{FLAG_AB} {x}: on | off") };
        let allowlist = arg(FLAG_ALLOWLIST).map(|s| pk_parse(FLAG_ALLOWLIST, &s)).transpose()?;
        let max_age_ms = match arg(FLAG_MAX_AGE) { Some(s) => s.parse::<u64>().map_err(|_| anyhow::anyhow!("{FLAG_MAX_AGE} {s}: whole milliseconds"))?, None => 2_000 };
        if !(1..=600_000).contains(&max_age_ms) { bail!("{FLAG_MAX_AGE} must be 1..600000 ms"); }
        if has(FLAG_MAX_AGE) && mode != Mode::Holders { bail!("{FLAG_MAX_AGE} needs {FLAG_MODE} holders"); }
        let curve_deep = match arg(FLAG_CURVE) {
            None => None,
            Some(s) => Some(s.parse::<f64>().ok().filter(|d| d.is_finite() && *d >= 0.05 && *d <= 0.9).with_context(|| format!("{FLAG_CURVE} {s}: D in [0.05, 0.9] (0.42 = abort when the price is 42% or more under the try's signing price)"))?),
        };
        Ok(Some(G43 { mode, program, n, theta, max_leavers, min_pct, ab, allowlist, max_age_ms, curve_deep }))
    }

    /// refused at start: a wallet the program will not accept
    pub fn check_wallet(&self, user: &Pk) -> Result<()> {
        if sgl::is_compiled(user) {
            if self.allowlist.is_some() { eprintln!("  GUARD: {FLAG_ALLOWLIST} ignored: wallet {} is compiled into the program (no list account on the tries)", b58(user)); }
            return Ok(());
        }
        if self.allowlist.is_none() { bail!("{FLAG_MODE}: wallet {} is not compiled into snipe-guard: add it to the allowlist PDA (ops/guard) and pass {FLAG_ALLOWLIST} <PDA>", b58(user)); }
        Ok(())
    }

    /// the run's banner line
    pub fn desc(&self) -> String {
        let m = match self.mode { Mode::Deadline => "deadline".to_string(),
            Mode::Holders => format!("holders {}:{}:{}:{} (abort when more than {} of the top {} below {:.0}%), max snapshot age {} ms", self.n, self.theta, self.max_leavers, self.min_pct,
                self.max_leavers, self.n, self.theta * 100.0, self.max_age_ms) };
        format!("GUARD (dip43 snipe-guard) {m}; program {}; {}{}{}", b58(&self.program), if self.ab { "A/B by window parity (odd: snipe-guard, even: Lighthouse)" } else { "every window" },
            self.allowlist.map(|l| format!("; allowlist {}", b58(&l))).unwrap_or_default(),
            self.curve_deep.map(|d| format!("; CURVE BAND LIVE (control key curve_deep): a try aborts when the price is >= {:.0}% under its signing price, on EVERY window (the A/B's Lighthouse arm: snipe-guard deadline + band, no floors)", d * 100.0)).unwrap_or_default())
    }

    /// does window `id` use the guard? (None = Lighthouse, dip42's)
    #[inline]
    pub fn uses(&self, id: u64) -> bool { !self.ab || id % 2 == 1 }

    /// the floors a try may carry from a window's set: 0 unless holders mode and a fresh snapshot (age at signing, `now` = mono ns)
    pub fn n_floors(&self, h: &HSet, now: u64) -> usize {
        if self.mode != Mode::Holders || h.why != WHY_OK || h.age_ms(now) > self.max_age_ms { return 0; }
        h.n as usize
    }
    /// one floor fewer (a try over 1,232 bytes); 0 when no more than max_leavers would be left (a check that cannot fail)
    pub fn shrink(&self, nf: usize) -> usize { let x = nf.saturating_sub(1); if x <= self.max_leavers as usize { 0 } else { x } }

    /// the guard instruction (the first `nf` floors of the window's set)
    pub fn ix(&self, user: Pk, deadline: u64, h: &HSet, nf: usize, curve: Option<(Pk, u64)>) -> build::Ix {
        let g = sgc::Guard { deadline: Some(deadline), floors: h.f[..nf.min(h.n as usize)].iter().map(|(a, f, _)| (*a, *f)).collect(),
            max_viol: if nf > 0 { self.max_leavers } else { 0 }, curve: curve.map(|(a, hi)| (a, 0, hi)), ..Default::default() };
        guard_ix(self.program, &g, user, self.allowlist)
    }

    /// the window's holder set at this book state (holders mode; else empty). `snap` from holders_for_floor
    pub fn hset(&self, snap: &Snap, user: &Pk, mint: &Pk, now: u64) -> HSet {
        let mut h = HSet::default();
        if self.mode != Mode::Holders { return h; }
        let Some(age) = snap.age_ms else { h.why = WHY_NO_SNAPSHOT; return h };
        if age > self.max_age_ms { h.why = WHY_STALE; h.t_snap = now.saturating_sub(age.saturating_mul(1_000_000)); return h; }
        let min = (self.min_pct / 100.0 * SUPPLY).ceil() as u64;
        let mut v: Vec<(Pk, u64)> = snap.holders.iter().filter(|(w, b)| w != user && *b >= min.max(1)).copied().collect();
        v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        v.truncate(self.n.min(MAXN));
        for (w, b) in v {
            let floor = ((b as f64 * self.theta) / sgl::UNIT as f64).floor().min(u32::MAX as f64) as u32;
            h.f[h.n as usize] = (snap.acct_of(&w).unwrap_or_else(|| ata_cached(&w, mint)), floor, w);
            h.n += 1;
        }
        h.t_snap = now.saturating_sub(age.saturating_mul(1_000_000));
        // a check that cannot fail (no more holders than may leave) is not sent
        if (h.n as usize) <= self.max_leavers as usize { h.why = WHY_FEW; }
        h
    }

    /// the try's `guard` field on presend_attempt (only with the guard configured): which guard, floors carried, why none, bytes
    pub fn rec(&self, used: bool, h: &HSet, nf: usize, dropped: usize, gix: &build::Ix, now: u64) -> serde_json::Value {
        if !used { return serde_json::json!({"mode": "lighthouse", "arm": "L"}); }
        let mut j = serde_json::json!({"mode": match self.mode { Mode::Deadline => "deadline", Mode::Holders => "holders" }, "n_floors": nf,
            "ix_bytes": 3 + gix.accounts.len() + gix.data.len(), "keys": gix.accounts.len().saturating_sub(1)});
        if self.ab { j["arm"] = "G".into(); }
        if self.mode == Mode::Holders {
            if nf > 0 {
                j["max_viol"] = self.max_leavers.into();
                j["floors"] = h.f[..nf].iter().map(|(_, f, w)| serde_json::json!([b58(w).chars().take(8).collect::<String>(), f])).collect::<Vec<_>>().into();
                j["age_ms"] = h.age_ms(now).into();
            } else {
                j["reason"] = match h.why { WHY_NO_SNAPSHOT => "no_snapshot", WHY_STALE => "stale", WHY_FEW => "few_holders",
                    _ => if h.n == 0 { "few_holders" } else if dropped > 0 { "size" } else { "stale" } }.into();
            }
            if dropped > 0 { j["dropped"] = dropped.into(); }
        }
        j
    }
}

impl PsLive {
    /// a window's holder floors now (empty unless --presend-live-guard holders): the arm / re-arm and every trade of an armed mint
    pub(super) fn g43_set(&self, mint: &Pk) -> HSet {
        match self.cfg.g43.as_ref() {
            Some(g) if g.mode == Mode::Holders => { let now = arbx::fast::mono_ns(); g.hset(&holders_for_floor(self.tbook(), mint, now), &self.user, mint, now) }
            _ => HSet::default(),
        }
    }
}

impl PsLive {
    /// holders mode: the armed window of `mint` takes fresh floors now (the true-balance snapshot just arrived; nothing in other modes)
    pub(super) fn g43_refresh(&self, mint: &Pk) {
        if !self.cfg.g43.as_ref().is_some_and(|g| g.mode == Mode::Holders) { return; }
        let Some(&id) = self.armed.get(mint) else { return };
        let hs = self.g43_set(mint);
        let mut g = self.sh.wins.lock().unwrap();
        if let Some(w) = g.iter_mut().find(|w| w.id == id) { w.g43 = hs; }
    }
}

/// one try's instructions as the sender builds them
pub struct GTry { pub ixs: Vec<build::Ix>, pub roles: pl::Roles, /// snipe-guard (false: Lighthouse, dip42's)
    pub used: bool, pub nf: usize, pub dropped: usize,
    /// dip43d: a Lighthouse-arm window's try that carried snipe-guard for the band (deadline + band, no floors); the band's upper bound
    pub l_arm: bool, pub curve_hi: Option<u64> }

/// THE SENDER'S TRY BUILDER (pure; the tests run the same function). `lighthouse(deadline)` = dip42's guard instruction,
/// `body(guard_ix)` = dip42's attempt around a guard instruction (attempt_ixs + the loaded-data limit). With the guard off (`g` None)
/// or on the A/B's Lighthouse arm: exactly `body(lighthouse(deadline))`, nothing else is called (dip42 byte for byte). With
/// snipe-guard: the floors the window's set allows now; a try whose compiled message would exceed 1,232 bytes drops floors from the
/// tail (a check that can no longer fail drops them all).
#[allow(clippy::too_many_arguments)]
pub fn try_ixs(g: Option<&G43>, w_id: u64, h: &HSet, now: u64, user: Pk, deadline: u64, bh: [u8; 32], lighthouse: impl Fn(u64) -> build::Ix,
               body: impl Fn(build::Ix) -> (Vec<build::Ix>, pl::Roles)) -> GTry {
    try_ixs_c(g, w_id, h, now, user, deadline, bh, None, lighthouse, body)
}
/// dip43d: try_ixs with the CURVE band (`curve` = (the curve's token account, upper bound); None = no band, dip43c byte for byte). With the band
/// the A/B's Lighthouse-arm windows carry snipe-guard too: deadline + band, no floors (`l_arm`).
#[allow(clippy::too_many_arguments)]
pub fn try_ixs_c(g: Option<&G43>, w_id: u64, h: &HSet, now: u64, user: Pk, deadline: u64, bh: [u8; 32], curve: Option<(Pk, u64)>, lighthouse: impl Fn(u64) -> build::Ix,
               body: impl Fn(build::Ix) -> (Vec<build::Ix>, pl::Roles)) -> GTry {
    let Some(g) = g.filter(|g| g.uses(w_id) || curve.is_some()) else {
        let (ixs, roles) = body(lighthouse(deadline));
        return GTry { ixs, roles, used: false, nf: 0, dropped: 0, l_arm: false, curve_hi: None };
    };
    let l_arm = !g.uses(w_id);
    let mut nf = if l_arm { 0 } else { g.n_floors(h, now) };
    let (mut ixs, mut roles) = body(g.ix(user, deadline, h, nf, curve));
    let mut dropped = 0usize;
    while nf > 0 && build::compile_v0(user, &ixs, bh, &[], &[]).is_ok_and(|m| m.bytes.len() + 65 > 1232) {
        nf = g.shrink(nf);
        dropped += 1;
        (ixs, roles) = body(g.ix(user, deadline, h, nf, curve));
    }
    GTry { ixs, roles, used: true, nf, dropped, l_arm, curve_hi: curve.map(|c| c.1) }
}

/// the guard instruction for any Guard (engine tries, the start-up check, the tests): the wallet first (a signer; it pays the try,
/// so no new key), the curve, the floors, the allowlist only for a wallet not compiled in
pub fn guard_ix(program: Pk, g: &sgc::Guard, user: Pk, allowlist: Option<Pk>) -> build::Ix {
    build::Ix { program, data: g.data(), accounts: g.accounts(user, allowlist).into_iter().map(|(key, signer, writable)| build::Meta { key, signer, writable }).collect() }
}

pub const WHY_OK: u8 = 0;
pub const WHY_NO_SNAPSHOT: u8 = 1;
pub const WHY_STALE: u8 = 2;
pub const WHY_FEW: u8 = 3;

/// a window's holder floors as the sender copies them (no allocation): (token account, floor in whole tokens, wallet)
#[derive(Clone, Copy, Debug, Default)]
pub struct HSet { pub n: u8, pub f: [(Pk, u32, Pk); MAXN], pub why: u8, /// mono ns of the snapshot the set was built from
    pub t_snap: u64 }
impl HSet {
    pub fn age_ms(&self, now: u64) -> u64 { now.saturating_sub(self.t_snap) / 1_000_000 }
}

/// a true-balance snapshot of a mint: (wallet, token balance raw) and its age (None: no true-balance snapshot)
#[derive(Clone, Debug, Default)]
pub struct Snap { pub holders: Vec<(Pk, u64)>, pub age_ms: Option<u64>,
    /// dip43c: holder -> its largest REAL token account (from the book; absent: the floor goes on the holder's ATA)
    pub accts: Vec<(Pk, Pk)> }
impl Snap { fn acct_of(&self, w: &Pk) -> Option<Pk> { self.accts.iter().find(|x| x.0 == *w).map(|x| x.1) } }

/// The holder provider for the floors (dip43 merge, 11-10): Builder A's true-balance book (A3, `--presend-live-tbal on`): the RPC read of
/// ALL the mint's token accounts at the arm (dip35's fam read), kept current by the pump trades' post balances; the bonding curve is never
/// a holder. `age_ms` = time since that snapshot ARRIVED (None: no book / no snapshot of this mint yet -> holders mode signs the deadline
/// only, reason "no_snapshot"; older than --presend-live-guard-max-age-ms -> "stale"). The engine's NET-TRADE book is never used for floors
/// (onchain REPORT §7 / verifier 11-10: net-trade floors measured worthless or harmful).
pub fn holders_for_floor(book: Option<&arbx::ps43_book::TBook>, mint: &Pk, now: u64) -> Snap {
    let Some(b) = book else { return Snap::default() };
    let Some((_, t)) = b.snap(mint) else { return Snap::default() };
    let holders = b.top_holders(mint, 4 * MAXN);
    let accts = holders.iter().filter_map(|(w, _)| b.acct_of(mint, w).map(|a| (*w, a))).collect();
    Snap { holders, age_ms: Some(now.saturating_sub(t) / 1_000_000), accts }
}

thread_local! {
    /// (wallet, mint) -> Token-2022 ATA (the main loop's thread; bounded)
    static ATAS: std::cell::RefCell<FxHashMap<(Pk, Pk), Pk>> = std::cell::RefCell::new(FxHashMap::default());
}
fn ata_cached(w: &Pk, mint: &Pk) -> Pk {
    ATAS.with(|c| {
        let mut m = c.borrow_mut();
        if let Some(a) = m.get(&(*w, *mint)) { return *a; }
        if m.len() > 50_000 { m.clear(); }
        let a = arbx::pda::ata(w, mint, &arbx::pda::TOKEN_2022);
        m.insert((*w, *mint), a);
        a
    })
}

/// the guard instruction's place in a signed try is index 2 (Roles.guard); a failure there on a snipe-guard try, decoded.
/// -> (the try's result, the guard_abort field). Nothing changes for a Lighthouse try (guard off, or the A/B's L arm).
pub fn reclassify(g: Option<&G43>, w: u64, res: String, err: &str) -> (String, Option<serde_json::Value>) { reclassify_sg(g, w, false, res, err) }
/// dip43d: `sg_l` = this Lighthouse-arm try carried snipe-guard (the band): decoded like a guard-arm try
pub fn reclassify_sg(g: Option<&G43>, w: u64, sg_l: bool, res: String, err: &str) -> (String, Option<serde_json::Value>) {
    let Some(g) = g else { return (res, None) };
    if !(g.uses(w) || sg_l) || res != "deadline" { return (res, None); }
    let code = err.split(":custom:0x").nth(1).and_then(|h| u32::from_str_radix(h.trim(), 16).ok());
    match code {
        None => ("guard_other".into(), Some(serde_json::json!({"raw": err}))),
        Some(c) => match sgc::decode(c) {
            None => ("guard_abort".into(), Some(serde_json::json!({"kind": "unknown", "code": format!("{c:#010x}")}))),
            Some(f) => {
                let j = abort_json(&f, c);
                (if f.kind == sgl::K_DEADLINE { "deadline".into() } else { "guard_abort".into() }, Some(j))
            }
        },
    }
}

/// guard_abort {kind, idx, cnt, gap_bucket, gap, sub?, code}
pub fn abort_json(f: &sgl::Fail, code: u32) -> serde_json::Value {
    let mut j = serde_json::json!({"kind": sgc::kind_name(f.kind), "idx": f.idx, "cnt": f.cnt, "gap_bucket": f.gap, "code": format!("{code:#010x}")});
    let gt = sgc::gap_text(f.kind, f.gap);
    if !gt.is_empty() { j["gap"] = gt.into(); }
    if let Some(s) = sgc::sub_name(f.kind, f.idx) { j["sub"] = s.into(); }
    j
}

/// START-UP CHECK (fail closed; simulation only, nothing sent): the program account is executable; a deadline 50 slots ahead passes;
/// one 50 slots behind fails at the guard with the decoded "deadline" kind; in holders mode a floor on a never-created account fails
/// with "floors". The wallet must be ours (compiled in, or listed with --presend-live-guard-allowlist).
pub async fn verify(rpc: &rpc::Rpc, key: &SigningKey, user: Pk, g: &G43) -> Result<()> {
    g.check_wallet(&user)?;
    let ai = rpc.call("getAccountInfo", serde_json::json!([b58(&g.program), { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 } }])).await.context("getAccountInfo(guard program)")?;
    if ai["value"].is_null() || ai["value"]["executable"].as_bool() != Some(true) { bail!("{FLAG_PROGRAM} {}: not an executable program on this cluster (deployed? ops/guard/DEPLOY.md)", b58(&g.program)); }
    let sim = |gd: sgc::Guard| async move {
        let ix = guard_ix(g.program, &gd, user, g.allowlist);
        let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]);
        let msg = build::compile_v0(user, &[build::cu_limit_ix(20_000), ix], bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
        let raw = build::sign(&msg, key);
        let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
        let v = rpc.call("simulateTransaction", serde_json::json!([b64, { "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" }])).await?;
        anyhow::Ok((v["value"]["err"].clone(), v["value"]["unitsConsumed"].as_u64().unwrap_or(0)))
    };
    let at_guard = |e: &serde_json::Value| -> Option<sgl::Fail> {
        let x = e.get("InstructionError")?;
        if x.get(0)?.as_u64()? != 1 { return None; }
        sgc::decode(x.get(1)?.get("Custom")?.as_u64()? as u32)
    };
    let s = rpc.slot().await.context("getSlot")?;
    let (e_ok, cu) = sim(sgc::Guard { deadline: Some(s + 50), ..Default::default() }).await?;
    if !e_ok.is_null() { bail!("{FLAG_MODE}: a deadline 50 slots ahead FAILED in simulation ({e_ok}{}) — refusing to start (fail closed)",
        at_guard(&e_ok).map(|f| format!(" = {}", abort_json(&f, 0))).unwrap_or_default()); }
    let (e_late, _) = sim(sgc::Guard { deadline: Some(s.saturating_sub(50)), ..Default::default() }).await?;
    if at_guard(&e_late).map(|f| f.kind) != Some(sgl::K_DEADLINE) { bail!("{FLAG_MODE}: a deadline 50 slots behind did not fail at the guard with its code ({e_late}) — refusing to start"); }
    let mut line = format!("GUARD verified on chain (simulated): snipe-guard {} deadline pass ({cu} CU incl. the CU-limit ix) / late -> deadline", b58(&g.program));
    if g.mode == Mode::Holders {
        // a never-created account holds 0: below a floor of 1 token, two of them = more than max_viol 1 -> floors
        let gone = |b: u8| { let mut k = [0u8; 32]; k[0] = 0x5e; k[1] = b; k[31] = 0x01; k };
        let (e_fl, _) = sim(sgc::Guard { deadline: Some(s + 50), floors: vec![(gone(1), 1), (gone(2), 1)], max_viol: 1, ..Default::default() }).await?;
        if at_guard(&e_fl).map(|f| f.kind) != Some(sgl::K_FLOORS) { bail!("{FLAG_MODE} holders: two empty floor accounts did not fail with the floors code ({e_fl}) — refusing to start"); }
        line.push_str(" / 2 empty floors -> floors");
    }
    eprintln!("{line}");
    Ok(())
}
