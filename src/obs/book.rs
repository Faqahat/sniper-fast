//! OBSERVATORY (dip24) shared per-token book, on the observatory thread only (never the event loop).
//! Every executed pump trade the engine saw goes in, in ARRIVAL order (the live engine's own order): the token's wallets and
//! balances (tokens bought - sold on the curve since the token's first trade we saw), the >= 6% holders, each wallet's first-buy
//! slot and create-slot insider mark, and a short recent tape (the last TAPE_NS of trades, at most TAPE_MAX) the modules read.
//! A token is `hist` when its CreateEvent was seen (balances complete); trades of other tokens get a book too (hist = false: their
//! holder figures are partial and every record says so). Bounded: tokens idle for IDLE_NS of feed time are retired, at most
//! MAX_TOKENS are kept (the longest idle go first), a token keeps at most MAX_WALLETS wallets (later wallets are not added:
//! counted); every retirement and cap hit is counted.
use crate::tx::Pk;
use rustc_hash::FxHashMap;
use std::collections::VecDeque;

/// pump.fun supply (raw units)
pub const SUPPLY: f64 = 1e15;
/// a ">= 6%" holder (raw tokens): 6% of the supply
pub const BIG: i64 = 60_000_000_000_000;
/// the curve is complete when a buy leaves the virtual token reserve at this (real token reserve 0; checked on the recording:
/// every CompleteEvent's trade has vtok == 279.9e12)
pub const COMPLETE_VTOK: u64 = 279_900_000_000_000;
/// the recent tape: trades of the last 12 s, at most 1024 per token
pub const TAPE_NS: u64 = 12_000_000_000;
pub const TAPE_MAX: usize = 1024;
/// a token with no trade for 30 min of feed time is retired
pub const IDLE_NS: u64 = 30 * 60 * 1_000_000_000;
pub const MAX_TOKENS: usize = 250_000;
pub const MAX_WALLETS: usize = 50_000;

/// tape flags (per trade, at the time of the trade)
pub const F_BIG: u8 = 1; // the trader held >= 6% before or after this trade
pub const F_CREATOR: u8 = 2;
pub const F_INSIDER: u8 = 4; // bought in the create slot (not the creator, not the create's signer)
pub const F_WATCHED: u8 = 8;
pub const F_OURS: u8 = 16; // our own wallet
pub const F_SIGNER: u8 = 32; // the create's signer

/// one executed curve trade as the observatory gets it
#[derive(Clone, Debug)]
pub struct Tr {
    pub mint: Pk, pub s: u64, pub i: u32, pub j: u32, pub t: u64, pub sig: [u8; 64], pub user: Pk, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64,
    pub vtok: u64, pub fbps: u16, pub cbps: u16,
}

impl Tr {
    /// post-trade price (lamports per raw token)
    #[inline] pub fn p(&self) -> f64 { self.vsol as f64 / (self.vtok as f64).max(1.0) }
    /// pre-trade price
    #[inline] pub fn p_pre(&self) -> f64 {
        let (v, t) = if self.buy { (self.vsol.saturating_sub(self.sol), self.vtok.saturating_add(self.tok)) } else { (self.vsol.saturating_add(self.sol), self.vtok.saturating_sub(self.tok)) };
        v as f64 / (t as f64).max(1.0)
    }
    /// pump's fee rate (protocol + creator, 95 / 30 bps when the event lacks them: the shadow's fee_rate)
    #[inline] pub fn fr(&self) -> f64 { crate::presend::fee_rate(self.fbps as u64, self.cbps as u64) }
    #[inline] pub fn pos(&self) -> (u64, u32, u32) { (self.s, self.i, self.j) }
}

/// one trade in a token's tape (what the records need), with its flags at that time
#[derive(Clone, Debug)]
pub struct TapeTr { pub s: u64, pub i: u32, pub j: u32, pub t: u64, pub user: Pk, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64, pub fr: f32, pub sig: [u8; 64], pub fl: u8, pub bal_after: i64 }

impl TapeTr {
    #[inline] pub fn p(&self) -> f64 { self.vsol as f64 / (self.vtok as f64).max(1.0) }
    #[inline] pub fn pos(&self) -> (u64, u32, u32) { (self.s, self.i, self.j) }
    /// the record form (wallet short = first 8 base58 characters; the full signature)
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"slot": self.s, "idx": self.i, "j": self.j, "t": self.t, "w": short(&self.user), "buy": self.buy, "sol": self.sol, "tok": self.tok,
            "vsol": self.vsol, "vtok": self.vtok, "fl": flags_str(self.fl), "pct_after": (self.bal_after.max(0) as f64 / SUPPLY * 1e4).round() / 100.0,
            "sig": bs58::encode(&self.sig).into_string()})
    }
}

pub fn short(k: &Pk) -> String { let s = bs58::encode(k).into_string(); s[..8.min(s.len())].to_string() }
pub fn b58(k: &Pk) -> String { bs58::encode(k).into_string() }
pub fn flags_str(f: u8) -> String {
    let mut s = String::new();
    for (b, c) in [(F_BIG, 'B'), (F_CREATOR, 'C'), (F_INSIDER, 'I'), (F_WATCHED, 'W'), (F_OURS, 'O'), (F_SIGNER, 'S')] { if f & b != 0 { s.push(c); } }
    s
}

#[derive(Clone, Copy, Debug, Default)]
pub struct W { pub bal: i64, pub first_buy: u64, pub ins: bool, pub n: u32 }

/// one followed token
pub struct Tok {
    pub mint: Pk,
    /// the CreateEvent was seen: s0 / t0 / creator / signer are real, the balances complete
    pub hist: bool,
    pub s0: u64, pub t0: u64, pub creator: Pk, pub signer: Pk, pub mayhem: bool,
    /// the study's non-standard-curve filter (any of its first 50 trades at curve < 25 / > 200 SOL, or no virtual tokens): not "normal"
    pub out: bool,
    pub n: u32,
    pub wal: FxHashMap<Pk, W>,
    /// wallets holding >= 6% now
    pub nbig: u32,
    /// the slot / time of the token's last trade, and of the trade before it (QUIET's since_last)
    pub last_s: u64, pub last_t: u64, pub prev_s: u64,
    /// the latest post-trade curve state
    pub vsol: u64, pub vtok: u64, pub fr: f32,
    pub tape: VecDeque<TapeTr>,
    /// the curve completed on this trade (slot, idx, t)
    pub complete: Option<(u64, u32, u64)>,
    /// wallets not added (MAX_WALLETS)
    pub wal_cap: u32,
}

impl Tok {
    /// a normal token: seen from its create, not mayhem, a standard curve
    #[inline] pub fn normal(&self) -> bool { self.hist && !self.mayhem && !self.out }
    pub fn age_slots(&self, s: u64) -> Option<u64> { self.hist.then(|| s.saturating_sub(self.s0)) }
    pub fn age_ms(&self, t: u64) -> Option<f64> { (self.hist && self.t0 > 0 && t >= self.t0).then(|| (t - self.t0) as f64 / 1e6) }
    /// the wallets holding >= 6% now, largest first: (wallet, balance, first-buy slot, flags)
    pub fn holders(&self) -> Vec<(Pk, i64, u64, u8)> {
        let mut v: Vec<(Pk, i64, u64, u8)> = self.wal.iter().filter(|(_, w)| w.bal >= BIG).map(|(k, w)| (*k, w.bal, w.first_buy, self.role(k, w))).collect();
        v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        v
    }
    pub fn role(&self, k: &Pk, w: &W) -> u8 {
        let mut f = 0;
        if self.hist && *k == self.creator { f |= F_CREATOR; }
        if self.hist && *k == self.signer { f |= F_SIGNER; }
        if w.ins { f |= F_INSIDER; }
        f
    }
    pub fn bal(&self, k: &Pk) -> i64 { self.wal.get(k).map(|w| w.bal).unwrap_or(0) }
    /// the tape entries with t in [lo, hi] (oldest first)
    pub fn tape_between(&self, lo: u64, hi: u64) -> impl Iterator<Item = &TapeTr> { self.tape.iter().filter(move |x| x.t >= lo && x.t <= hi) }
}

/// what a trade meant for the book (returned by `apply`)
#[derive(Clone, Copy, Debug, Default)]
pub struct Ctx {
    pub hist: bool, pub normal: bool, pub bal_before: i64, pub bal_after: i64, pub nbig_before: u32, pub nbig_after: u32, pub fl: u8,
    /// the token's previous trade slot (0: none)
    pub prev_s: u64,
    /// this trade completed the curve
    pub completes: bool,
    /// the token's trade count before this one
    pub n_before: u32,
}

#[derive(Clone, Debug, Default)]
pub struct Stats { pub creates: u64, pub mayhem: u64, pub trades: u64, pub no_hist_trades: u64, pub retired: u64, pub evicted: u64, pub wal_capped: u64, pub excluded: u64, pub completes: u64 }

pub struct Book {
    pub toks: FxHashMap<Pk, Box<Tok>>,
    pub user: Pk,
    pub st: Stats,
    last_sweep_t: u64,
    pub max_t: u64,
}

impl Book {
    pub fn new(user: Pk) -> Book { let mut toks = FxHashMap::default(); toks.reserve(1 << 14); Book { toks, user, st: Stats::default(), last_sweep_t: 0, max_t: 0 } }
    pub fn get(&self, m: &Pk) -> Option<&Tok> { self.toks.get(m).map(|b| &**b) }

    fn fresh(mint: Pk, hist: bool, s0: u64, t0: u64, creator: Pk, signer: Pk, mayhem: bool) -> Box<Tok> {
        Box::new(Tok { mint, hist, s0, t0, creator, signer, mayhem, out: false, n: 0, wal: FxHashMap::default(), nbig: 0, last_s: s0, last_t: t0, prev_s: 0, vsol: 0, vtok: 0,
            fr: 0.0125, tape: VecDeque::new(), complete: None, wal_cap: 0 })
    }

    /// a CreateEvent (its executed tx): the token is followed from here
    pub fn create(&mut self, mint: Pk, s: u64, t: u64, creator: Pk, signer: Pk, mayhem: bool) {
        self.st.creates += 1;
        if mayhem { self.st.mayhem += 1; }
        match self.toks.get_mut(&mint) {
            // trades seen before the create (a reordered delivery): the book becomes a full one only if nothing traded yet
            Some(t0) => { if t0.n == 0 { **t0 = *Self::fresh(mint, true, s, t, creator, signer, mayhem); } }
            None => { self.toks.insert(mint, Self::fresh(mint, true, s, t, creator, signer, mayhem)); }
        }
    }

    /// one trade (arrival order): the book after it; `watched` marks the trader
    pub fn apply(&mut self, tr: &Tr, watched: bool) -> Ctx {
        self.st.trades += 1;
        self.max_t = self.max_t.max(tr.t);
        let user = self.user;
        let tk = self.toks.entry(tr.mint).or_insert_with(|| Self::fresh(tr.mint, false, tr.s, 0, [0; 32], [0; 32], false));
        if !tk.hist { self.st.no_hist_trades += 1; }
        // the study's non-standard curves (as presend / presend_live: one of the first 50 trades at curve < 25 / > 200 SOL, or no vtok)
        if tk.hist && !tk.out && tk.n < 50 && (tr.vsol < 25_000_000_000 || tr.vsol > 200_000_000_000 || tr.vtok == 0) { tk.out = true; self.st.excluded += 1; }
        let n_before = tk.n;
        tk.n += 1;
        let prev_s = if n_before == 0 { 0 } else { tk.last_s };
        tk.prev_s = prev_s;
        tk.last_s = tk.last_s.max(tr.s);
        tk.last_t = tk.last_t.max(tr.t);
        tk.vsol = tr.vsol; tk.vtok = tr.vtok; tk.fr = tr.fr() as f32;
        let nbig_before = tk.nbig;
        let (hist, s0, creator, signer) = (tk.hist, tk.s0, tk.creator, tk.signer);
        let full = tk.wal.len() >= MAX_WALLETS && !tk.wal.contains_key(&tr.user);
        let (bal_before, bal_after, role) = if full {
            tk.wal_cap += 1; self.st.wal_capped += 1;
            (0, 0, 0)
        } else {
            let w = tk.wal.entry(tr.user).or_default();
            let b0 = w.bal;
            if tr.buy { w.bal += tr.tok as i64; if w.first_buy == 0 { w.first_buy = tr.s; } } else { w.bal -= tr.tok as i64; }
            w.n += 1;
            if hist && tr.buy && tr.s == s0 && tr.user != creator && tr.user != signer { w.ins = true; }
            let b1 = w.bal;
            let mut role = 0u8;
            if hist && tr.user == creator { role |= F_CREATOR; }
            if hist && tr.user == signer { role |= F_SIGNER; }
            if w.ins { role |= F_INSIDER; }
            (b0, b1, role)
        };
        if bal_before < BIG && bal_after >= BIG { tk.nbig += 1; }
        if bal_before >= BIG && bal_after < BIG { tk.nbig = tk.nbig.saturating_sub(1); }
        let mut fl = role;
        if bal_before >= BIG || bal_after >= BIG { fl |= F_BIG; }
        if watched { fl |= F_WATCHED; }
        if tr.user == user { fl |= F_OURS; }
        let completes = tr.buy && tr.vtok <= COMPLETE_VTOK && tk.complete.is_none();
        if completes { tk.complete = Some((tr.s, tr.i, tr.t)); self.st.completes += 1; }
        // the recent tape
        let lo = tr.t.saturating_sub(TAPE_NS);
        while tk.tape.front().is_some_and(|x| x.t < lo) || tk.tape.len() >= TAPE_MAX { tk.tape.pop_front(); }
        tk.tape.push_back(TapeTr { s: tr.s, i: tr.i, j: tr.j, t: tr.t, user: tr.user, buy: tr.buy, sol: tr.sol, tok: tr.tok, vsol: tr.vsol, vtok: tr.vtok, fr: tr.fr() as f32,
            sig: tr.sig, fl, bal_after });
        Ctx { hist, normal: tk.normal(), bal_before, bal_after, nbig_before, nbig_after: tk.nbig, fl, prev_s, completes, n_before }
    }

    /// retire tokens idle for IDLE_NS (feed time) unless `keep` says a module still needs them; cap MAX_TOKENS; tapes of tokens idle
    /// for TAPE_NS are freed. Runs at most every 10 s of feed time
    pub fn sweep(&mut self, keep: &dyn Fn(&Pk) -> bool) {
        if self.max_t < self.last_sweep_t + 10_000_000_000 { return; }
        self.last_sweep_t = self.max_t;
        let now = self.max_t;
        let n0 = self.toks.len();
        self.toks.retain(|m, t| now.saturating_sub(t.last_t.max(t.t0)) < IDLE_NS || keep(m));
        self.st.retired += (n0 - self.toks.len()) as u64;
        for t in self.toks.values_mut() {
            if !t.tape.is_empty() && now.saturating_sub(t.last_t) > TAPE_NS { t.tape = VecDeque::new(); }
        }
        if self.toks.len() > MAX_TOKENS {
            let mut v: Vec<(u64, Pk)> = self.toks.iter().map(|(m, t)| (t.last_t.max(t.t0), *m)).collect();
            v.sort_unstable();
            let k = self.toks.len() - MAX_TOKENS * 9 / 10;
            for (_, m) in v.into_iter().take(k) { if !keep(&m) { self.toks.remove(&m); self.st.evicted += 1; } }
        }
    }

    /// rough memory use (bytes): token boxes, wallet maps, tapes
    pub fn mem_bytes(&self) -> usize {
        self.toks.values().map(|t| std::mem::size_of::<Tok>() + t.wal.capacity() * (32 + std::mem::size_of::<W>() + 8) + t.tape.capacity() * std::mem::size_of::<TapeTr>()).sum::<usize>()
            + self.toks.capacity() * 48
    }
}

/// SOL out (lamports, before pump's fee) of selling `q` raw tokens on the curve (v, t) (pump's integer constant product)
#[inline]
pub fn sell_out(v: f64, t: f64, q: f64) -> f64 { if t + q <= 0.0 { 0.0 } else { v * q / (t + q) } }

/// tokens a buy of `sol_in` lamports (fee on top: sol_in / (1 + fr) reaches the curve) gets on (v, t), and the SOL that reached it
#[inline]
pub fn buy_tokens(v: f64, t: f64, sol_in: f64, fr: f64) -> (f64, f64) { let x = sol_in / (1.0 + fr); ((t * x / (v + x)).floor(), x) }

/// a position on a curve: the curve with us in it; trades after our buy applied in order. `naive`: every later trade applied as it
/// was (its SOL in for a buy, its tokens in for a sell); `slip`: a later buy whose min-out our buy breaks (the study's slack table,
/// by signature) is dropped (presend.rs Path, the "model" variant)
#[derive(Clone, Debug)]
pub struct Pos { pub size: f64, pub q: f64, pub v: f64, pub t: f64, pub fr: f64, pub slip: bool, pub dropped: u32 }

impl Pos {
    /// our buy of `size` lamports right after the state (v, t) with fee rate fr. None: untradeable (curve >= 100 SOL or nothing bought)
    pub fn open(v: u64, t: u64, size: f64, fr: f64, slip: bool) -> Option<Pos> {
        if v >= 100_000_000_000 || v == 0 || t == 0 { return None; }
        let (q, x) = buy_tokens(v as f64, t as f64, size, fr);
        if q < 1.0 { return None; }
        Some(Pos { size, q, v: v as f64 + x, t: t as f64 - q, fr, slip, dropped: 0 })
    }
    /// one later trade (not ours)
    pub fn feed(&mut self, x: &TapeTr) {
        if x.buy {
            let sol = x.sol as f64; let dt = (self.t * sol / (self.v + sol)).floor();
            if self.slip && dt < x.tok as f64 / (1.0 + crate::presend::slack_of_sig(&bs58::encode(&x.sig).into_string())) { self.dropped += 1; return; }
            self.v += sol; self.t -= dt;
        } else {
            let tk = x.tok as f64; let so = (self.v * tk / (self.t + tk)).floor(); self.v -= so; self.t += tk;
        }
        self.fr = x.fr as f64;
    }
    /// SOL back (after pump's fee) if we sold everything now
    pub fn out(&self) -> f64 { sell_out(self.v, self.t, self.q) * (1.0 - self.fr) }
    /// value ratio (SOL back / size)
    pub fn val(&self) -> f64 { self.out() / self.size }
    /// gross P&L (lamports)
    pub fn pnl(&self) -> f64 { self.out() - self.size }
}
