// =====================================================================================================================
// dip45 FLEET SIGNAL SHADOW (owner 11-11: push plan step 1, "log-only shadow, no sends, nothing that changes any decision").
// Spec: /home/it/sniper-studies/push4-audit/REPORT.md section 6 "what the shadow must log"; docs/dip45_fleet.md.
// With --presend-live-fleet-log off (the default) nothing of it exists: no thread, no record, no field (dip43g byte for byte).
//
//  1. DETECTOR. Every arrival (the shred / entries / deshred feeds = BEFORE execution, and the executed feed) is matched against the
//     fleet's transaction SHAPE, independent of the signer (the fleet rotates one wallet every ~85 min): <= 1 signer, no lookup
//     tables, exactly the layout CB SetComputeUnitLimit, CB SetComputeUnitPrice, CB SetLoadedAccountsDataSizeLimit, Lighthouse (02),
//     Lighthouse (0f, the slot assertion), System CreateAccountWithSeed, Token-2022 InitializeAccount3, pump buy e1f7501ed5b38488 (no tip
//     transfer anywhere: the layout has none). Class "fleet" = that layout AND the CU price in the signature's set / ranges AND the CU
//     limit in its range; "shape" = the layout with a CU price / limit outside (signature drift, counted, never in the flags). Our own
//     wallet is never counted. The signature comes built in or from --presend-live-fleet-sig FILE (JSON, re-read when it changes).
//  2. STATE per token: the fleet tries (de-duplicated across feeds by signature) of the last 64 slots; flags at (mint, slot S): tries in
//     slot S-1, S-2..S-1, S-3..S-1, S-8..S-1, in S so far, distinct signers S-8..S, the fleet arm's first slot, the last try slot.
//  3. RECORDS "presend_live_fleet" by "stage": config | sig | fleet_arm (one per fleet arm = tries on a token with gaps <= 5 slots:
//     per slot pre-exec / exec counts and whether a pre-exec sighting came before the slot ended) | arm / fill (OUR live or dry
//     windows' arms and fills, flags at that moment) | shadow_arm / shadow_fill (the pre-send shadow's paper arms / would-fills: the
//     DRY run's fills) | follow (per fill / would-fill: the dump before it, the first other buyer after the dump, later buys / sells
//     in the 3 slots after) | silent / back (no fleet try for 30 min) ; the status line's "FLEET LOG" part; run_end "fleet".
// HOW: the event loop classifies (one length compare for almost every tx) and hands hits, slot starts, the watched tokens' trades
// and our arm / fill records to the thread "fleet-log" (the tests: inline). The engine reads nothing back.
// =====================================================================================================================
use super::*;
use std::collections::BTreeMap;
use std::sync::RwLock;

pub const LIGHTHOUSE: &str = "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95";
/// tries kept per token (slots)
pub const KEEP_SLOTS: u64 = 64;
/// a fleet arm ends after this many slots without a try (the audit's arms_from: gaps <= 5)
pub const ARM_GAP: u64 = 5;
/// silence alarm (ns of feed time)
pub const SILENT_NS: u64 = 30 * 60 * 1_000_000_000;
/// our arms / fills followed for trades (slots)
pub const WATCH_ARM: u64 = 64;
pub const WATCH_FILL: u64 = 8;
pub const FOLLOW_SLOTS: u64 = 3;
const SIG_CHECK: Duration = Duration::from_secs(10);

fn pk_of(s: &str) -> Result<Pk> { bs58::decode(s).into_vec().ok().and_then(|v| v.try_into().ok()).ok_or_else(|| anyhow::anyhow!("not a public key: {s}")) }
fn alias(s: &str) -> Result<Pk> {
    Ok(match s {
        "cb" => arbx::tx::COMPUTE_BUDGET, "lh" => pk_of(LIGHTHOUSE)?, "sys" => [0u8; 32], "t22" => pk_of("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")?,
        "spl" => pk_of("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")?, "ata" => pk_of("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")?,
        "pump" => pk_of("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")?, x => pk_of(x)?,
    })
}

#[derive(Clone, Debug)]
pub struct FleetCfg { pub sig: Option<String> }
impl FleetCfg { pub fn json(&self) -> serde_json::Value { serde_json::json!({"sig": self.sig}) } }

/// the fleet signature (built in, or the file)
#[derive(Clone, Debug, PartialEq)]
pub struct Sig {
    pub prices: Vec<u64>,
    pub ranges: Vec<(u64, u64)>,
    pub cul: (u32, u32),
    /// (program, data prefix) per instruction, in order
    pub layout: Vec<(Pk, Vec<u8>, String)>,
    /// the mint: instruction `mint_ix`'s account `mint_acc`
    pub mint_ix: usize,
    pub mint_acc: usize,
    pub max_signers: u8,
}

pub const DEFAULT_SIG: &str = r#"{"cu_prices": [32000], "cu_price_ranges": [[11000, 13500]], "cu_limit": [40000, 80000],
 "layout": ["cb:02", "cb:03", "cb:04", "lh:02", "lh:0f", "sys:03000000", "t22:12", "pump:e1f7501ed5b38488"], "mint_ix": 7, "mint_acc": 1, "max_signers": 1}"#;

impl Sig {
    pub fn builtin() -> Sig { Sig::parse(DEFAULT_SIG.as_bytes()).unwrap() }
    pub fn parse(b: &[u8]) -> Result<Sig> {
        let v: serde_json::Value = serde_json::from_slice(b)?;
        let prices: Vec<u64> = v["cu_prices"].as_array().map(|a| a.iter().filter_map(|x| x.as_u64()).collect()).unwrap_or_default();
        let mut ranges = Vec::new();
        for r in v["cu_price_ranges"].as_array().cloned().unwrap_or_default() {
            let (a, b) = (r[0].as_u64(), r[1].as_u64());
            match (a, b) { (Some(a), Some(b)) if a <= b => ranges.push((a, b)), _ => bail!("cu_price_ranges: [[lo, hi], ...]") }
        }
        let cul = match (v["cu_limit"][0].as_u64(), v["cu_limit"][1].as_u64()) { (Some(a), Some(b)) if a <= b => (a as u32, b as u32), _ => bail!("cu_limit: [lo, hi]") };
        let mut layout = Vec::new();
        for s in v["layout"].as_array().ok_or_else(|| anyhow::anyhow!("layout: [\"prog:hexprefix\", ...]"))? {
            let s = s.as_str().ok_or_else(|| anyhow::anyhow!("layout entries are strings"))?;
            let (p, h) = s.split_once(':').unwrap_or((s, ""));
            let d = (0..h.len() / 2).map(|i| u8::from_str_radix(&h[2 * i..2 * i + 2], 16)).collect::<Result<Vec<u8>, _>>().map_err(|_| anyhow::anyhow!("bad hex in {s}"))?;
            if h.len() % 2 != 0 { bail!("bad hex in {s}"); }
            layout.push((alias(p)?, d, s.to_string()));
        }
        if layout.is_empty() { bail!("layout is empty"); }
        let mint_ix = v["mint_ix"].as_u64().unwrap_or(layout.len() as u64 - 1) as usize;
        if mint_ix >= layout.len() { bail!("mint_ix out of the layout"); }
        if prices.is_empty() && ranges.is_empty() { bail!("no cu_prices / cu_price_ranges"); }
        Ok(Sig { prices, ranges, cul, layout, mint_ix, mint_acc: v["mint_acc"].as_u64().unwrap_or(1) as usize, max_signers: v["max_signers"].as_u64().unwrap_or(1) as u8 })
    }
    pub fn price_ok(&self, p: u64) -> bool { self.prices.contains(&p) || self.ranges.iter().any(|r| (r.0..=r.1).contains(&p)) }
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"cu_prices": self.prices, "cu_price_ranges": self.ranges.iter().map(|r| [r.0, r.1]).collect::<Vec<_>>(), "cu_limit": [self.cul.0, self.cul.1],
            "layout": self.layout.iter().map(|l| l.2.clone()).collect::<Vec<_>>(), "mint_ix": self.mint_ix, "mint_acc": self.mint_acc, "max_signers": self.max_signers})
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Class { Fleet, Shape }
#[derive(Clone, Copy, Debug)]
pub struct Hit { pub class: Class, pub mint: Pk, pub signer: Pk, pub cu_price: u64, pub cu_limit: u32 }

/// the shape test (signer-free). Almost every tx leaves at the instruction count.
pub fn classify(tx: &arbx::tx::Tx, s: &Sig) -> Option<Hit> {
    if tx.ixs.len() != s.layout.len() || tx.is_vote || !tx.lookups.is_empty() || tx.num_signers > s.max_signers || tx.num_signers == 0 { return None; }
    let (mut price, mut limit) = (None, None);
    for (ix, (p, pre, _)) in tx.ixs.iter().zip(&s.layout) {
        if tx.keys.get(ix.program as usize)? != p || !ix.data.starts_with(pre) { return None; }
        if *p == arbx::tx::COMPUTE_BUDGET {
            match ix.data.first() {
                Some(2) if ix.data.len() >= 5 => limit = Some(u32::from_le_bytes(ix.data[1..5].try_into().unwrap())),
                Some(3) if ix.data.len() >= 9 => price = Some(u64::from_le_bytes(ix.data[1..9].try_into().unwrap())),
                _ => {}
            }
        }
    }
    let mi = &tx.ixs[s.mint_ix];
    let mint = *tx.keys.get(*mi.accounts.get(s.mint_acc)? as usize)?;
    let (price, limit) = (price.unwrap_or(0), limit.unwrap_or(0));
    let class = if s.price_ok(price) && (s.cul.0..=s.cul.1).contains(&limit) { Class::Fleet } else { Class::Shape };
    Some(Hit { class, mint, signer: tx.keys[0], cu_price: price, cu_limit: limit })
}

// ---- the state ----------------------------------------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct Try { pub sig8: u64, pub slot: u64, pub signer: Pk, pub t: u64, pub mono: u64, pub feed: u16, pub pre: bool, pub exec: bool, pub feeds: u32, pub t_pre: u64 }

#[derive(Clone, Debug, Default)]
pub struct ArmAgg { pub s0: u64, pub s1: u64, pub signers: Vec<Pk>, pub n: u32, pub cups: BTreeMap<u64, u32>, pub cul: (u32, u32), pub first_t: u64, pub first_mono: u64, pub first_feed: u16,
    pub first_pre: bool, pub sigs: Vec<u64> }

#[derive(Default)]
pub struct FTok { pub tries: VecDeque<Try>, pub arm: Option<ArmAgg>, pub trades: Vec<FT>, pub watch: u64 }

#[derive(Clone, Copy, Debug)]
pub struct FT { pub slot: u64, pub idx: u32, pub j: u16, pub user: Pk, pub buy: bool, pub sol: u64, pub ours: bool }
impl FT { fn pos(&self) -> (u64, u32, u16) { (self.slot, self.idx, self.j) } }

/// our arm / fill (live or dry), or the shadow's paper arm / would-fill
#[derive(Clone, Debug)]
pub struct OurEv { pub stage: &'static str, pub w: u64, pub kind: String, pub mint: Pk, pub slot: u64, pub idx: Option<u32>, pub dump: Option<(u64, u32)>, pub sig: Option<String>,
    pub sol_in: Option<u64>, pub dry: bool }

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Flags { pub n0: u32, pub n1: u32, pub n2: u32, pub n3: u32, pub n8: u32, pub pre8: u32, pub signers8: u32, pub first_slot: Option<u64>, pub last_slot: Option<u64> }
impl Flags {
    pub fn json(&self, slot: u64) -> serde_json::Value {
        serde_json::json!({"n0": self.n0, "n1": self.n1, "n2": self.n2, "n3": self.n3, "n8": self.n8, "pre8": self.pre8, "signers8": self.signers8,
            "first_slot": self.first_slot, "last_slot": self.last_slot, "gap": self.last_slot.map(|l| slot.saturating_sub(l)), "on2": self.n2 > 0, "on8": self.n8 > 0})
    }
}

#[derive(Default)]
pub struct FStats { pub tries: AtomicU64, pub pre: AtomicU64, pub exec: AtomicU64, pub exec_only: AtomicU64, pub shape: AtomicU64, pub arms: AtomicU64, pub slots: AtomicU64,
    pub slots_pre_end: AtomicU64, pub slots_exec_only: AtomicU64, pub our_arms: AtomicU64, pub our_arms8: AtomicU64, pub our_fills: AtomicU64, pub our_fills8: AtomicU64,
    pub sh_fills: AtomicU64, pub sh_fills8: AtomicU64, pub follows: AtomicU64, pub dropped: AtomicU64 }

pub struct Fleet {
    pub sig: Arc<RwLock<Arc<Sig>>>,
    pub sig_src: String,
    sig_mtime: Option<std::time::SystemTime>,
    sig_at: Instant,
    pub cfg: FleetCfg,
    pub toks: FxHashMap<Pk, FTok>,
    /// open fleet arms (their mints)
    open: FxHashSet<Pk>,
    /// first arrival (wall ns) of each slot on any feed
    starts: BTreeMap<u64, u64>,
    pub slot: u64,
    pub t_now: u64,
    t_start: u64,
    t_last_try: u64,
    pub silent: bool,
    silent_n: u32,
    signers: FxHashMap<Pk, (u64, u64, u32)>,
    arm_ts: VecDeque<u64>,
    shape_cups: BTreeMap<u64, u32>,
    fleet_cups: BTreeMap<u64, u32>,
    follows: Vec<(OurEv, (u64, u32, u16))>,
    pub feeds: Vec<String>,
    pub st: Arc<FStats>,
}

impl Fleet {
    pub fn open(cfg: FleetCfg) -> (Fleet, Option<String>) {
        let mut f = Fleet { sig: Arc::new(RwLock::new(Arc::new(Sig::builtin()))), sig_src: "built-in".into(), sig_mtime: None, sig_at: Instant::now(), cfg, toks: FxHashMap::default(),
            open: FxHashSet::default(), starts: BTreeMap::new(), slot: 0, t_now: 0, t_start: 0, t_last_try: 0, silent: false, silent_n: 0, signers: FxHashMap::default(),
            arm_ts: VecDeque::new(), shape_cups: BTreeMap::new(), fleet_cups: BTreeMap::new(), follows: Vec::new(), feeds: Vec::new(), st: Arc::new(FStats::default()) };
        let err = f.sig_load().err().map(|e| e.to_string());
        (f, err)
    }

    fn sig_load(&mut self) -> Result<bool> {
        let Some(p) = self.cfg.sig.clone() else { return Ok(false) };
        let m = std::fs::metadata(&p).and_then(|m| m.modified()).ok();
        if m.is_some() && m == self.sig_mtime { return Ok(false); }
        self.sig_mtime = m;
        let s = Sig::parse(&std::fs::read(&p)?).map_err(|e| anyhow::anyhow!("{p}: {e}"))?;
        let changed = **self.sig.read().unwrap() != s;
        *self.sig.write().unwrap() = Arc::new(s);
        self.sig_src = p;
        Ok(changed)
    }

    /// the file's change check (every 10 s): a change -> a "sig" record; an error keeps the signature in use
    pub fn sig_check(&mut self, force: bool, out: &mut Vec<serde_json::Value>) {
        if self.cfg.sig.is_none() || (!force && self.sig_at.elapsed() < SIG_CHECK) { return; }
        self.sig_at = Instant::now();
        match self.sig_load() {
            Ok(true) => out.push(serde_json::json!({"ev": "presend_live_fleet", "stage": "sig", "src": self.sig_src, "sig": self.sig.read().unwrap().json()})),
            Ok(false) => {}
            Err(e) => out.push(serde_json::json!({"ev": "presend_live_fleet", "stage": "sig", "err": e.to_string(), "kept": self.sig.read().unwrap().json()})),
        }
    }

    pub fn config_rec(&self, err: &Option<String>) -> serde_json::Value {
        serde_json::json!({"ev": "presend_live_fleet", "stage": "config", "mode": "log", "sig_src": self.sig_src, "sig": self.sig.read().unwrap().json(), "err": err,
            "keep_slots": KEEP_SLOTS, "arm_gap": ARM_GAP, "silent_min": SILENT_NS / 60_000_000_000, "follow_slots": FOLLOW_SLOTS})
    }

    /// the start of a slot on any feed (its first arrival): the slot clock; fleet arms past their gap end; follows due; the silence check
    pub fn slot_start(&mut self, slot: u64, t: u64, out: &mut Vec<serde_json::Value>) {
        if self.t_start == 0 { self.t_start = t; self.t_last_try = t; }
        self.t_now = self.t_now.max(t);
        self.starts.entry(slot).or_insert(t);
        while self.starts.len() > 4096 { let k = *self.starts.keys().next().unwrap(); self.starts.remove(&k); }
        if slot <= self.slot { return; }
        self.slot = slot;
        // fleet arms that ended
        let done: Vec<Pk> = self.open.iter().filter(|m| self.toks.get(*m).and_then(|t| t.arm.as_ref()).is_none_or(|a| slot > a.s1 + ARM_GAP)).copied().collect();
        for m in done { self.open.remove(&m); self.arm_close(&m, out); }
        // follows due
        let due: Vec<usize> = (0..self.follows.len()).filter(|&i| slot > self.follows[i].1 .0 + FOLLOW_SLOTS).collect();
        for i in due.into_iter().rev() { let (e, land) = self.follows.remove(i); self.follow_rec(&e, land, out); }
        // prune
        if slot % 64 == 0 {
            let lo = slot.saturating_sub(KEEP_SLOTS);
            self.toks.retain(|_, t| {
                while t.tries.front().is_some_and(|x| x.slot < lo) { t.tries.pop_front(); }
                t.trades.retain(|x| x.slot + 200 >= slot);
                !t.tries.is_empty() || t.arm.is_some() || t.watch >= slot
            });
            let tl = self.t_now.saturating_sub(SILENT_NS);
            self.signers.retain(|_, v| v.1 >= tl.saturating_sub(23 * 3600 * 1_000_000_000));
        }
        while self.arm_ts.front().is_some_and(|&x| x + 24 * 3600 * 1_000_000_000 < self.t_now) { self.arm_ts.pop_front(); }
        // silence
        if !self.silent && self.t_now.saturating_sub(self.t_last_try) > SILENT_NS {
            self.silent = true; self.silent_n += 1;
            out.push(serde_json::json!({"ev": "presend_live_fleet", "stage": "silent", "t": self.t_now, "slot": slot, "last_try_t": self.t_last_try,
                "min": self.t_now.saturating_sub(self.t_last_try) / 60_000_000_000}));
        }
    }

    /// one sighting of a fleet-shape tx (any feed). pre = an unexecuted feed (shreds / entries / deshred)
    #[allow(clippy::too_many_arguments)]
    pub fn sighting(&mut self, h: &Hit, sig8: u64, slot: u64, t: u64, mono: u64, feed: u16, pre: bool, out: &mut Vec<serde_json::Value>) {
        if h.class == Class::Shape { self.st.shape.fetch_add(1, Ordering::Relaxed); *self.shape_cups.entry(h.cu_price).or_default() += 1; return; }
        if self.t_start == 0 { self.t_start = t; }
        self.t_now = self.t_now.max(t);
        let tok = self.toks.entry(h.mint).or_default();
        let bit = 1u32 << (feed.min(31));
        if let Some(x) = tok.tries.iter_mut().rev().find(|x| x.sig8 == sig8) {
            if pre && !x.pre { x.t_pre = t; }
            if !x.pre && pre { self.st.pre.fetch_add(1, Ordering::Relaxed); }
            if !x.exec && !pre { self.st.exec.fetch_add(1, Ordering::Relaxed); }
            x.pre |= pre; x.exec |= !pre; x.feeds |= bit;
            return;
        }
        self.st.tries.fetch_add(1, Ordering::Relaxed);
        if pre { self.st.pre.fetch_add(1, Ordering::Relaxed); } else { self.st.exec.fetch_add(1, Ordering::Relaxed); }
        let pos = tok.tries.partition_point(|x| x.slot <= slot);
        tok.tries.insert(pos, Try { sig8, slot, signer: h.signer, t, mono, feed, pre, exec: !pre, feeds: bit, t_pre: if pre { t } else { 0 } });
        *self.fleet_cups.entry(h.cu_price).or_default() += 1;
        // the fleet arm
        let new_arm = tok.arm.as_ref().is_none_or(|a| slot > a.s1 + ARM_GAP);
        if new_arm && tok.arm.is_some() { self.open.remove(&h.mint); self.arm_close(&h.mint, out); }
        let tok = self.toks.get_mut(&h.mint).unwrap();
        let a = tok.arm.get_or_insert_with(|| ArmAgg { s0: slot, s1: slot, first_t: t, first_mono: mono, first_feed: feed, first_pre: pre, cul: (u32::MAX, 0), ..Default::default() });
        a.s0 = a.s0.min(slot); a.s1 = a.s1.max(slot); a.n += 1; a.sigs.push(sig8);
        if !a.signers.contains(&h.signer) { a.signers.push(h.signer); }
        *a.cups.entry(h.cu_price).or_default() += 1;
        a.cul = (a.cul.0.min(h.cu_limit), a.cul.1.max(h.cu_limit));
        self.open.insert(h.mint);
        let s = self.signers.entry(h.signer).or_insert((t, t, 0)); s.1 = s.1.max(t); s.2 += 1;
        self.t_last_try = self.t_last_try.max(t);
        if self.silent {
            self.silent = false;
            out.push(serde_json::json!({"ev": "presend_live_fleet", "stage": "back", "t": t, "slot": slot, "signer": b58(&h.signer), "mint": b58(&h.mint)}));
        }
    }

    fn slot_end(&self, s: u64) -> Option<u64> { self.starts.range(s + 1..).next().map(|x| *x.1) }

    fn arm_close(&mut self, m: &Pk, out: &mut Vec<serde_json::Value>) {
        let Some(tok) = self.toks.get_mut(m) else { return };
        let Some(a) = tok.arm.take() else { return };
        // per slot: [tries, pre-exec, exec, pre-exec seen before the slot ended]
        let mut per: BTreeMap<u64, [u32; 5]> = BTreeMap::new();
        let mut feeds = [0u32; 8];
        for x in tok.tries.iter().filter(|x| a.sigs.contains(&x.sig8)) {
            let e = per.entry(x.slot).or_default();
            e[0] += 1;
            if x.pre { e[1] += 1; }
            if x.exec { e[2] += 1; }
            if x.exec && !x.pre { e[4] += 1; }
            for (k, f) in feeds.iter_mut().enumerate() { if x.feeds & (1 << k) != 0 { *f += 1; } }
        }
        let ends: Vec<(u64, Option<u64>)> = per.keys().map(|&s| (s, self.slot_end(s))).collect();
        let tok = self.toks.get_mut(m).unwrap();
        for (s, end) in &ends {
            if let Some(end) = end {
                let n = tok.tries.iter().filter(|x| x.slot == *s && a.sigs.contains(&x.sig8) && x.pre && x.t_pre > 0 && x.t_pre < *end).count() as u32;
                per.get_mut(s).unwrap()[3] = n;
            }
        }
        let n_slots = per.len() as u64;
        let pre_end = per.values().filter(|v| v[3] > 0).count() as u64;
        let exec_only = per.values().filter(|v| v[1] == 0).count() as u64;
        self.st.arms.fetch_add(1, Ordering::Relaxed);
        self.st.slots.fetch_add(n_slots, Ordering::Relaxed);
        self.st.slots_pre_end.fetch_add(pre_end, Ordering::Relaxed);
        self.st.slots_exec_only.fetch_add(exec_only, Ordering::Relaxed);
        self.st.exec_only.fetch_add(per.values().map(|v| v[4] as u64).sum(), Ordering::Relaxed);
        self.arm_ts.push_back(a.first_t);
        let first_ms = self.starts.get(&a.s0).map(|&s0| (a.first_t as i64 - s0 as i64) as f64 / 1e6);
        out.push(serde_json::json!({"ev": "presend_live_fleet", "stage": "fleet_arm", "mint": b58(m), "s0": a.s0, "s1": a.s1, "n": a.n,
            "signers": a.signers.iter().map(b58).collect::<Vec<_>>(), "cups": a.cups.iter().map(|(k, v)| [*k, *v as u64]).collect::<Vec<_>>(), "cul": [a.cul.0, a.cul.1],
            "first": {"t": a.first_t, "mono": a.first_mono, "feed": a.first_feed, "feed_name": self.feeds.get(a.first_feed as usize), "pre": a.first_pre, "ms_after_slot_start": first_ms},
            "slots": per.iter().map(|(s, v)| [s - a.s0, v[0] as u64, v[1] as u64, v[2] as u64, v[3] as u64]).collect::<Vec<_>>(),
            "n_slots": n_slots, "slots_pre_by_end": pre_end, "slots_exec_only": exec_only, "per_feed": feeds}));
    }

    /// the flags at (mint, slot): tries of earlier slots, and of this slot seen so far
    pub fn flags(&self, m: &Pk, slot: u64) -> Flags {
        let mut f = Flags::default();
        let Some(t) = self.toks.get(m) else { return f };
        let mut sg: Vec<Pk> = Vec::new();
        for x in t.tries.iter().filter(|x| x.slot <= slot) {
            let d = slot - x.slot;
            if d == 0 { f.n0 += 1; }
            if d == 1 { f.n1 += 1; }
            if (1..=2).contains(&d) { f.n2 += 1; }
            if (1..=3).contains(&d) { f.n3 += 1; }
            if (1..=8).contains(&d) { f.n8 += 1; if x.pre { f.pre8 += 1; } }
            if d <= 8 && !sg.contains(&x.signer) { sg.push(x.signer); }
            f.last_slot = Some(f.last_slot.map_or(x.slot, |l: u64| l.max(x.slot)));
        }
        f.signers8 = sg.len() as u32;
        f.first_slot = t.arm.as_ref().filter(|a| a.s0 <= slot).map(|a| a.s0).or_else(|| t.tries.iter().find(|x| x.slot <= slot).map(|x| x.slot));
        f
    }

    pub fn trade(&mut self, m: &Pk, x: FT) {
        let t = self.toks.entry(*m).or_default();
        let pos = t.trades.partition_point(|y| y.pos() <= x.pos());
        t.trades.insert(pos, x);
    }

    pub fn our(&mut self, e: OurEv, out: &mut Vec<serde_json::Value>) {
        let f = self.flags(&e.mint, e.slot);
        let (c, c8) = match e.stage {
            "arm" => (&self.st.our_arms, &self.st.our_arms8), "fill" => (&self.st.our_fills, &self.st.our_fills8),
            "shadow_fill" => (&self.st.sh_fills, &self.st.sh_fills8), _ => (&self.st.dropped, &self.st.dropped),
        };
        if e.stage != "shadow_arm" { c.fetch_add(1, Ordering::Relaxed); if f.n8 > 0 { c8.fetch_add(1, Ordering::Relaxed); } }
        let mut r = serde_json::json!({"ev": "presend_live_fleet", "stage": e.stage, "w": e.w, "kind": e.kind, "mint": b58(&e.mint), "slot": e.slot, "dry": e.dry,
            "t": self.t_now, "fleet": f.json(e.slot), "fleet_arm_open": self.open.contains(&e.mint)});
        if let Some(i) = e.idx { r["idx"] = i.into(); }
        if let Some(s) = &e.sig { r["sig"] = s.clone().into(); }
        if let Some(s) = e.sol_in { r["sol_in"] = s.into(); }
        if let Some((s, i)) = e.dump { r["dump"] = serde_json::json!([s, i]); }
        out.push(r);
        let watch = if e.stage.ends_with("arm") { e.slot + WATCH_ARM } else { e.slot + WATCH_FILL };
        let t = self.toks.entry(e.mint).or_default(); t.watch = t.watch.max(watch);
        if e.stage.ends_with("fill") {
            // our landing: the fill's own position; a would-fill: just after its dump
            let land = match (e.idx, e.dump) { (Some(i), _) => (e.slot, i, 0), (None, Some((s, i))) => (s, i, u16::MAX), _ => (e.slot, u32::MAX, 0) };
            self.follows.push((e, land));
        }
    }

    /// the follower monitor of one fill / would-fill
    fn follow_rec(&mut self, e: &OurEv, land: (u64, u32, u16), out: &mut Vec<serde_json::Value>) {
        self.st.follows.fetch_add(1, Ordering::Relaxed);
        let empty = Vec::new();
        let tr = self.toks.get(&e.mint).map_or(&empty, |t| &t.trades);
        let dump = match e.dump {
            Some((s, i)) => tr.iter().find(|x| x.slot == s && x.idx == i && !x.buy),
            None => tr.iter().rev().find(|x| !x.buy && !x.ours && x.pos() < land && x.slot + 8 >= land.0),
        };
        let first_buy = dump.and_then(|d| tr.iter().find(|x| x.buy && !x.ours && x.pos() > d.pos()));
        let after = |x: &&FT| x.pos() > land && x.slot <= land.0 + FOLLOW_SLOTS && !x.ours;
        let lb: u64 = tr.iter().filter(after).filter(|x| x.buy).map(|x| x.sol).sum();
        let ls: u64 = tr.iter().filter(after).filter(|x| !x.buy).map(|x| x.sol).sum();
        let nb = { let mut v: Vec<Pk> = tr.iter().filter(after).filter(|x| x.buy).map(|x| x.user).collect(); v.sort(); v.dedup(); v.len() };
        let mut r = serde_json::json!({"ev": "presend_live_fleet", "stage": "follow", "of": e.stage, "w": e.w, "kind": e.kind, "mint": b58(&e.mint), "slot": e.slot,
            "land": [land.0, if land.1 == u32::MAX { serde_json::Value::Null } else { land.1.into() }], "later_buy_sol": lb, "later_sell_sol": ls, "later_buyers": nb,
            "trades_seen": tr.len()});
        if let Some(d) = dump {
            r["dump"] = serde_json::json!({"slot": d.slot, "idx": d.idx, "sol": d.sol, "user": &b58(&d.user)[..8]});
            r["first_buyer"] = match first_buy {
                Some(b) => serde_json::json!({"slot": b.slot, "idx": b.idx, "sol": b.sol, "user": &b58(&b.user)[..8], "dslot": b.slot - d.slot,
                    "dpos": if b.slot == d.slot { serde_json::Value::from(b.idx as i64 - d.idx as i64) } else { serde_json::Value::Null },
                    "ours_first": land.2 == 0 && land.1 != u32::MAX && land < b.pos()}),
                None => serde_json::Value::Null,
            };
        }
        out.push(r);
    }

    fn arms_day(&self) -> f64 {
        let h = self.t_now.saturating_sub(self.t_start) as f64 / 3.6e12;
        if h <= 0.0 { 0.0 } else { self.arm_ts.len() as f64 / h.min(24.0) * 24.0 }
    }
    fn signers_30m(&self) -> usize { self.signers.values().filter(|v| v.1 + SILENT_NS >= self.t_now).count() }

    pub fn status(&self) -> String {
        let s = &self.st; let l = |a: &AtomicU64| a.load(Ordering::Relaxed);
        let pct = |a: u64, b: u64| if b == 0 { "-".to_string() } else { format!("{:.0}%", a as f64 * 100.0 / b as f64) };
        format!(" | FLEET LOG: tries {} (pre-exec {}, exec {}, exec-only {}) slots {} (pre-exec by slot end {}) arms {} (~{:.0}/day) signers30m {} sig {} (shape-only {}) \
            | ours: arms {}/{} fills {}/{} would-fills {}/{} (fleet in 8 slots) | last try {} s ago{}",
            l(&s.tries), l(&s.pre), l(&s.exec), l(&s.exec_only), l(&s.slots), pct(l(&s.slots_pre_end), l(&s.slots)), l(&s.arms), self.arms_day(), self.signers_30m(),
            pct(l(&s.tries), l(&s.tries) + l(&s.shape)), l(&s.shape), l(&s.our_arms8), l(&s.our_arms), l(&s.our_fills8), l(&s.our_fills), l(&s.sh_fills8), l(&s.sh_fills),
            self.t_now.saturating_sub(self.t_last_try) / 1_000_000_000, if self.silent { " SILENT >30 min" } else { "" })
    }

    pub fn finish(&mut self, out: &mut Vec<serde_json::Value>) -> serde_json::Value {
        let open: Vec<Pk> = self.open.drain().collect();
        for m in open { self.arm_close(&m, out); }
        let fl: Vec<(OurEv, (u64, u32, u16))> = std::mem::take(&mut self.follows);
        for (e, land) in fl { self.follow_rec(&e, land, out); }
        let s = &self.st; let l = |a: &AtomicU64| a.load(Ordering::Relaxed);
        let mut sg: Vec<_> = self.signers.iter().map(|(k, v)| (v.0, b58(k), v.1, v.2)).collect(); sg.sort();
        serde_json::json!({"mode": "log", "sig_src": self.sig_src, "tries": l(&s.tries), "pre": l(&s.pre), "exec": l(&s.exec), "exec_only": l(&s.exec_only), "shape_only": l(&s.shape),
            "arms": l(&s.arms), "arms_day": self.arms_day(), "slots": l(&s.slots), "slots_pre_by_end": l(&s.slots_pre_end), "slots_exec_only": l(&s.slots_exec_only),
            "signers": sg.iter().map(|x| serde_json::json!({"signer": x.1, "first_t": x.0, "last_t": x.2, "tries": x.3})).collect::<Vec<_>>(),
            "fleet_cups": self.fleet_cups.iter().map(|(k, v)| [*k, *v as u64]).collect::<Vec<_>>(), "shape_cups": self.shape_cups.iter().map(|(k, v)| [*k, *v as u64]).collect::<Vec<_>>(),
            "ours": {"arms": l(&s.our_arms), "arms_fleet8": l(&s.our_arms8), "fills": l(&s.our_fills), "fills_fleet8": l(&s.our_fills8), "would_fills": l(&s.sh_fills),
                "would_fills_fleet8": l(&s.sh_fills8)}, "follows": l(&s.follows), "silent_periods": self.silent_n, "silent_now": self.silent, "dropped": l(&s.dropped)})
    }
}

// ---- the thread ---------------------------------------------------------------------------------------------------------

pub enum FMsg { Hit(Hit, u64, u64, u64, u64, u16, bool), Slot(u64, u64), Trade(Pk, FT), Our(Box<OurEv>), Feeds(Vec<String>), Finish(crossbeam_channel::Sender<serde_json::Value>) }

pub struct FleetTap {
    tx: Option<crossbeam_channel::Sender<FMsg>>,
    inline: Option<Box<Fleet>>,
    out: crossbeam_channel::Sender<Out>,
    thread: Option<std::thread::JoinHandle<()>>,
    pub sig: Arc<RwLock<Arc<Sig>>>,
    status: Arc<Mutex<String>>,
    /// the event loop's side: the highest slot seen, the watched tokens (until slot)
    pub max_slot: u64,
    pub watch: FxHashMap<Pk, u64>,
    pub user: Pk,
}

fn emit(out: &crossbeam_channel::Sender<Out>, recs: &mut Vec<serde_json::Value>) { for r in recs.drain(..) { let _ = out.send(Out::Rec(r)); } }

fn apply(f: &mut Fleet, m: FMsg, recs: &mut Vec<serde_json::Value>) {
    match m {
        FMsg::Hit(h, sig8, slot, t, mono, feed, pre) => f.sighting(&h, sig8, slot, t, mono, feed, pre, recs),
        FMsg::Slot(s, t) => f.slot_start(s, t, recs),
        FMsg::Trade(m, x) => f.trade(&m, x),
        FMsg::Our(e) => f.our(*e, recs),
        FMsg::Feeds(v) => f.feeds = v,
        FMsg::Finish(_) => {}
    }
}

impl FleetTap {
    pub fn start(cfg: FleetCfg, user: Pk, out: &crossbeam_channel::Sender<Out>, inline: bool) -> FleetTap {
        let (mut f, err) = Fleet::open(cfg);
        eprintln!("DIP FLEET SIGNAL SHADOW (dip45, LOG ONLY: nothing sent, no decision changed): fleet-shape tries on every feed (pre-exec + executed), signature {} {}{} \
            | per token tries in the last 1/2/3/8 slots on our arms / fills / would-fills | follower monitor {FOLLOW_SLOTS} slots | silent after {} min",
            f.sig_src, f.sig.read().unwrap().json(), err.as_ref().map(|e| format!(" | SIG FILE ERROR {e} (built-in kept)")).unwrap_or_default(), SILENT_NS / 60_000_000_000);
        let _ = out.send(Out::Rec(f.config_rec(&err)));
        let sig = f.sig.clone();
        let status = Arc::new(Mutex::new(String::new()));
        let base = FleetTap { tx: None, inline: None, out: out.clone(), thread: None, sig, status: status.clone(), max_slot: 0, watch: FxHashMap::default(), user };
        if inline { return FleetTap { inline: Some(Box::new(f)), ..base }; }
        let (tx, rx) = crossbeam_channel::unbounded::<FMsg>();
        let o = out.clone();
        let thread = std::thread::Builder::new().name("fleet-log".into()).spawn(move || {
            let mut recs = Vec::new();
            let mut at = Instant::now();
            loop {
                match rx.recv_timeout(Duration::from_secs(1)) {
                    Ok(FMsg::Finish(r)) => { let j = f.finish(&mut recs); emit(&o, &mut recs); let _ = r.send(j); return; }
                    Ok(m) => apply(&mut f, m, &mut recs),
                    Err(crossbeam_channel::RecvTimeoutError::Timeout) => {}
                    Err(crossbeam_channel::RecvTimeoutError::Disconnected) => return,
                }
                if at.elapsed() >= Duration::from_secs(1) { at = Instant::now(); f.sig_check(false, &mut recs); *status.lock().unwrap() = f.status(); }
                if !recs.is_empty() { emit(&o, &mut recs); }
            }
        }).ok();
        FleetTap { tx: Some(tx), thread, ..base }
    }

    fn send(&mut self, m: FMsg) {
        if let Some(f) = self.inline.as_mut() { let mut recs = Vec::new(); apply(f, m, &mut recs); emit(&self.out, &mut recs); return; }
        if let Some(tx) = &self.tx { let _ = tx.send(m); }
    }

    pub fn feeds(&mut self, names: Vec<String>) { self.send(FMsg::Feeds(names)); }

    /// every arrival (the event loop, first thing in on_arrival): the slot clock, and the shape test
    /// dip47: -> a fleet-CLASS try's (mint, slot, signature's first 8 bytes) for the re-arm fleet rule (None: no hit / "shape" only / ours)
    pub fn arrival(&mut self, a: &arbx::feeds::Arrival) -> Option<(Pk, u64, u64)> {
        if a.slot > self.max_slot { self.max_slot = a.slot; self.send(FMsg::Slot(a.slot, a.t_rx)); }
        let hit = { let s = self.sig.read().unwrap(); if a.tx.ixs.len() != s.layout.len() { return None; } classify(&a.tx, &s) };
        let h = hit?;
        if h.signer == self.user { return None; }
        let sig8 = u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap());
        let r = (h.class == Class::Fleet).then_some((h.mint, a.slot, sig8));
        self.send(FMsg::Hit(h, sig8, a.slot, a.t_rx, arbx::fast::mono_ns(), a.feed, a.executed.is_none()));
        r
    }

    /// an executed pump tx: the trades of the watched tokens
    pub fn exec(&mut self, a: &arbx::feeds::Arrival, x: &arbx::feeds::ExecInfo) {
        if self.watch.is_empty() { return; }
        for (j, e) in x.trades.iter().enumerate() {
            if self.watch.get(&e.mint).is_some_and(|&u| u >= a.slot) {
                let ft = FT { slot: a.slot, idx: x.index as u32, j: j as u16, user: e.user, buy: e.buy, sol: e.sol, ours: e.user == self.user };
                self.send(FMsg::Trade(e.mint, ft));
            }
        }
    }

    fn watch_add(&mut self, m: Pk, until: u64) {
        let e = self.watch.entry(m).or_insert(0); *e = (*e).max(until);
        if self.watch.len() > 4096 { let s = self.max_slot; self.watch.retain(|_, u| *u >= s); }
    }

    /// a record of ours (live / dry): arms and fills are annotated
    pub fn on_rec(&mut self, v: &serde_json::Value) {
        let ev = v["ev"].as_str().unwrap_or("");
        let stage = match ev { "presend_live_arm" => "arm", "presend_live_fill" => "fill", _ => return };
        // a T2 arm names its token in "trig", a re-arm in "mint"; the trigger / dump trade's position (arms)
        let Some(mint) = v["mint"].as_str().or(v["trig"]["mint"].as_str()).and_then(|s| pk_of(s).ok()) else { return };
        let d = if v["trig"].is_object() { &v["trig"] } else { &v["dump"] };
        let dump = if stage == "arm" { d["slot"].as_u64().map(|s| (s, d["idx"].as_u64().unwrap_or(0) as u32)) } else { None };
        let slot = if stage == "fill" { v["slot"].as_u64().unwrap_or(self.max_slot) } else { self.max_slot };
        let kind = v["kind"].as_str().unwrap_or("t2").to_string();
        let e = OurEv { stage, w: v["w"].as_u64().unwrap_or(0), kind, mint, slot, idx: v["idx"].as_u64().map(|x| x as u32), dump,
            sig: v["sig"].as_str().map(String::from), sol_in: v["sol_in"].as_u64(), dry: v["dry"].as_bool().unwrap_or(false) };
        self.watch_add(mint, slot + if stage == "arm" { WATCH_ARM } else { WATCH_FILL });
        self.send(FMsg::Our(Box::new(e)));
    }

    /// the pre-send shadow's records: its paper arms and would-fills (the dry run's fills)
    pub fn on_shadow(&mut self, v: &serde_json::Value) {
        let ev = v["ev"].as_str().unwrap_or("");
        let (stage, kind) = match ev { "presend_arm" => ("shadow_arm", "shadow"), "presend_fill" => ("shadow_fill", "shadow"), "presend_wide_fill" => ("shadow_fill", "wide"),
            "presend_wide_arm" => ("shadow_arm", "wide"), _ => return };
        let Some(mint) = v["mint"].as_str().and_then(|s| pk_of(s).ok()) else { return };
        let dump = v["x"]["slot"].as_u64().map(|s| (s, v["x"]["idx"].as_u64().unwrap_or(0) as u32));
        let slot = if stage == "shadow_fill" { v["s_in"].as_u64().or(dump.map(|d| d.0)).unwrap_or(self.max_slot) } else { v["slot"].as_u64().unwrap_or(self.max_slot) };
        let row = v["row"].as_str().map(|r| format!("{kind}:{r}")).unwrap_or_else(|| kind.to_string());
        let e = OurEv { stage, w: v["w"].as_u64().unwrap_or(0), kind: row, mint, slot, idx: None, dump: if stage == "shadow_fill" { dump } else { None }, sig: None, sol_in: None, dry: true };
        self.watch_add(mint, slot + if stage == "shadow_arm" { WATCH_ARM } else { WATCH_FILL });
        self.send(FMsg::Our(Box::new(e)));
    }

    pub fn status(&self) -> String {
        if let Some(f) = self.inline.as_ref() { return f.status(); }
        self.status.lock().unwrap().clone()
    }

    pub fn finish(&mut self) -> Option<serde_json::Value> {
        if let Some(f) = self.inline.as_mut() { let mut recs = Vec::new(); let j = f.finish(&mut recs); emit(&self.out, &mut recs); return Some(j); }
        let tx = self.tx.take()?;
        let (rtx, rrx) = crossbeam_channel::bounded(1);
        let _ = tx.send(FMsg::Finish(rtx));
        let j = rrx.recv_timeout(Duration::from_secs(20)).ok();
        if j.is_some() { if let Some(t) = self.thread.take() { let _ = t.join(); } }
        Some(j.unwrap_or_else(|| serde_json::json!({"mode": "log", "err": "the fleet thread did not answer in 20 s"})))
    }

    #[cfg(test)]
    pub fn inner(&self) -> Option<&Fleet> { self.inline.as_deref() }
}
