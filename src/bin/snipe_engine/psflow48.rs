// =====================================================================================================================
// dip48 FOLLOWER-FLOW LOG (LOG ONLY; --presend-live-flow-log on, default off = dip47 byte for byte). Never a decision, send, fee or exit.
// Why: trigdisc2 PLAN.md §4 (lever 3): outside buys in slots fill .. fill+1 after our pre-send fill describe the bounce (AUC 0.82 / 0.72),
// bought mostly by the registry dip bots. Measured live on every fill for later exit / size / regime work.
// CLASSES (the study's s4_fills.py, exclusive, in this order): us (our wallet) | dumper (the window's whale / re-arm dumper) | fleet (the
// trade's tx invokes the Lighthouse program L2TExMFK..., the study's "fleet program") | bots (the registry: the bot-depth list the engine
// loaded, --presend-live-botdepth-list = the study's botdepth_wallets.json) | rivals (the study's 15 named prefixes + 2y2iF8fA +
// --presend-live-tag-wallets) | retail (everyone else = the study's "quick" + "retail").
// WHAT: for every pre-send fill (T2, re-arm, wide) the trades on the mint AFTER our buy in slots fill, fill+1, fill+2, fill+3: per slot offset
// and class buy SOL / sell SOL / counts, distinct outside buyers, the curve price after the slot's last trade. Closed when a slot > fill+3
// is seen (tick) or at the position's exit, whichever first.
// Records: "presend_live_flow" {w, mint, kind, fill_slot, closed (slot3 | exit), per_slot [{dslot, buy_sol {class: SOL}, sell_sol, n_buys,
// n_sells, n_buyers, price}], tot1 / tot2 (outside = all but us, through fill+1 / +2)}; presend_live_realized gets "flow" {b1, b2, s1, s2,
// fleet1, bots1, retail1}; one line per fill. O(1) per trade (one map lookup per trade; the class only for a tracked mint), main loop only.
// =====================================================================================================================
use super::*;

pub const FLAG: &str = "--presend-live-flow-log";
pub const CLASSES: [&str; 6] = ["us", "dumper", "fleet", "bots", "rivals", "retail"];
pub const RIVALS: [&str; 16] = ["haqq6qnV", "4ggJqUDD", "DL7cmioG", "8yYMhu", "E2x1", "9pQQc1xy", "8PgC4ngp", "2NUMEzNh", "3qvuM3U5", "rem3dgec", "peMU8nX3", "DF7eRX",
    "7tg5VGSe", "CkbAaKua", "HkQ7hMjy", "2y2iF8fA"];
pub const SLOTS: u64 = 3;
static LIGHTHOUSE_PK: std::sync::LazyLock<Pk> = std::sync::LazyLock::new(|| bs58::decode(ps45_fleet::LIGHTHOUSE).into_vec().unwrap().try_into().unwrap());

/// the tx invokes Lighthouse (the study's fleet program class)
pub fn is_fleet_tx(tx: &arbx::tx::Tx) -> bool { tx.ixs.iter().any(|ix| tx.keys.get(ix.program as usize) == Some(&*LIGHTHOUSE_PK)) }

#[derive(Clone, Debug, Default)]
pub struct Slot { pub buy: [u64; 6], pub sell: [u64; 6], pub nb: [u32; 6], pub ns: [u32; 6], pub buyers: Vec<Pk>, pub price: f64 }

#[derive(Clone, Debug)]
pub struct FW { pub w: u64, pub mint: Pk, pub kind: &'static str, pub fill: (u64, u32, i32), pub dumper: Pk, pub s: [Slot; 4], pub price0: f64 }

impl FW {
    pub fn new(w: u64, mint: Pk, kind: &'static str, fill: (u64, u32, i32), dumper: Pk, price0: f64) -> FW {
        FW { w, mint, kind, fill, dumper, s: Default::default(), price0 }
    }
    /// one trade of the mint (class index `c`); false: outside the window (before our buy / after fill+3)
    pub fn add(&mut self, pos: (u64, u32, i32), user: Pk, buy: bool, sol: u64, price: f64, c: usize) -> bool {
        if pos <= self.fill || pos.0 > self.fill.0 + SLOTS { return false; }
        let s = &mut self.s[(pos.0 - self.fill.0) as usize];
        if buy { s.buy[c] += sol; s.nb[c] += 1; if c != 0 && !s.buyers.contains(&user) { s.buyers.push(user); } } else { s.sell[c] += sol; s.ns[c] += 1; }
        s.price = price;
        true
    }
    /// outside (all but us) buy / sell SOL through fill+n; one class's buys through fill+n
    pub fn tot(&self, n: usize, buy: bool) -> f64 { self.s[..=n].iter().map(|s| (if buy { &s.buy } else { &s.sell })[1..].iter().sum::<u64>()).sum::<u64>() as f64 / 1e9 }
    pub fn cls(&self, n: usize, c: usize) -> f64 { self.s[..=n].iter().map(|s| s.buy[c]).sum::<u64>() as f64 / 1e9 }
    pub fn json(&self, closed: &str) -> serde_json::Value {
        let r = |x: f64| (x * 1e6).round() / 1e6;
        let by = |a: &[u64; 6]| -> serde_json::Value { CLASSES.iter().zip(a).map(|(k, v)| (k.to_string(), serde_json::json!(r(*v as f64 / 1e9)))).collect::<serde_json::Map<_, _>>().into() };
        let mut last = self.price0;
        let ps: Vec<serde_json::Value> = self.s.iter().enumerate().map(|(d, s)| {
            if s.price > 0.0 { last = s.price; }
            serde_json::json!({"dslot": d, "buy_sol": by(&s.buy), "sell_sol": by(&s.sell), "n_buys": s.nb.iter().sum::<u32>(), "n_sells": s.ns.iter().sum::<u32>(),
                "n_buyers": s.buyers.len(), "price": last})
        }).collect();
        let tot = |n: usize| serde_json::json!({"buy": r(self.tot(n, true)), "sell": r(self.tot(n, false)), "fleet": r(self.cls(n, 2)), "bots": r(self.cls(n, 3)), "rivals": r(self.cls(n, 4)),
            "retail": r(self.cls(n, 5)), "dumper": r(self.cls(n, 1))});
        serde_json::json!({"ev": "presend_live_flow", "w": self.w, "mint": b58(&self.mint), "kind": self.kind, "fill_slot": self.fill.0, "fill_idx": self.fill.1, "closed": closed,
            "price_fill": self.price0, "per_slot": ps, "tot1": tot(1), "tot2": tot(2)})
    }
    pub fn compact(&self) -> serde_json::Value {
        let r = |x: f64| (x * 1e6).round() / 1e6;
        serde_json::json!({"b1": r(self.tot(1, true)), "b2": r(self.tot(2, true)), "s1": r(self.tot(1, false)), "s2": r(self.tot(2, false)), "fleet1": r(self.cls(1, 2)),
            "bots1": r(self.cls(1, 3)), "retail1": r(self.cls(1, 5))})
    }
    pub fn line(&self) -> String {
        let p = |n: usize| format!("+{n} buys {:.2} (bots {:.2}, fleet {:.2}, retail {:.2}) sells {:.2}", self.tot(n, true), self.cls(n, 3), self.cls(n, 2), self.cls(n, 5), self.tot(n, false));
        format!("  PRESEND LIVE FLOW (log) w{} {}: {} | {}", self.w, b58(&self.mint), p(1), p(2))
    }
}

#[derive(Default)]
pub struct Flow48 {
    pub open: FxHashMap<Pk, Vec<FW>>,
    pub done: FxHashMap<u64, serde_json::Value>,
    done_q: VecDeque<u64>,
    pub tag: FxHashSet<Pk>,
    pub n_trades: u64, pub ns: std::cell::Cell<u64>, pub fills: u64, pub closed: u64,
}

impl Flow48 {
    pub fn new(tag: &[Pk]) -> Flow48 { Flow48 { tag: tag.iter().copied().collect(), ..Default::default() } }
    fn finish(&mut self, f: FW) -> (serde_json::Value, String) {
        self.done.insert(f.w, f.compact());
        self.done_q.push_back(f.w);
        while self.done_q.len() > 4096 { if let Some(o) = self.done_q.pop_front() { self.done.remove(&o); } }
        self.closed += 1;
        (f.json(""), f.line())
    }
}

/// a wallet's class (not us / the dumper / fleet: those are known before)
pub fn rival_or_bot(user: &Pk, bots: Option<&FxHashSet<Pk>>, tag: &FxHashSet<Pk>) -> usize {
    if bots.is_some_and(|b| b.contains(user)) { return 3; }
    if tag.contains(user) { return 4; }
    let s = b58(user);
    if RIVALS.iter().any(|r| s.starts_with(r)) { 4 } else { 5 }
}

impl PsLive {
    /// a trade the detector took (on_exec; nothing with the log off): O(1) unless its mint has a fill being followed
    pub(super) fn fl48_trade(&mut self, t: &pl::Trade, tx: &arbx::tx::Tx) {
        let Some(f) = self.fl48.as_ref() else { return };
        if !f.open.contains_key(&t.mint) { return; }
        let t0 = arbx::fast::mono_ns();
        let bots = self.bd.as_ref().and_then(|b| b.set.as_ref());
        let user = self.user;
        let fleet = is_fleet_tx(tx);
        let f = self.fl48.as_mut().unwrap();
        let tag = std::mem::take(&mut f.tag);
        if let Some(v) = f.open.get_mut(&t.mint) {
            for fw in v.iter_mut() {
                let c = if t.user == user { 0 } else if t.user == fw.dumper { 1 } else if fleet { 2 } else { rival_or_bot(&t.user, bots, &tag) };
                fw.add(t.pos(), t.user, t.buy, t.sol, t.p(), c);
            }
        }
        f.tag = tag;
        f.n_trades += 1;
        f.ns.set(f.ns.get() + arbx::fast::mono_ns().saturating_sub(t0));
    }
    /// a pre-send fill: follow its mint's trades for 4 slots
    pub(super) fn fl48_fill(&mut self, w: u64, t: &pl::Trade) {
        if self.fl48.is_none() { return; }
        let kind = self.g47_kind(w);
        let dumper = self.wins.get(&w).map_or([0u8; 32], |x| x.whale);
        let f = self.fl48.as_mut().unwrap();
        if f.done.contains_key(&w) || f.open.values().flatten().any(|x| x.w == w) { return; }
        f.fills += 1;
        f.open.entry(t.mint).or_default().push(FW::new(w, t.mint, kind, t.pos(), dumper, t.p()));
    }
    /// close the fills whose fill+3 passed (tick) or window `exit_w`'s at its exit
    pub(super) fn fl48_close(&mut self, slot_now: u64, exit_w: Option<u64>) {
        let Some(f) = self.fl48.as_mut() else { return };
        if f.open.is_empty() { return; }
        let mut out = Vec::new();
        f.open.retain(|_, v| {
            let mut keep = Vec::new();
            for fw in v.drain(..) {
                if exit_w == Some(fw.w) { out.push((fw, "exit")); } else if slot_now > fw.fill.0 + SLOTS { out.push((fw, "slot3")); } else { keep.push(fw); }
            }
            *v = keep;
            !v.is_empty()
        });
        for (fw, why) in out {
            let f = self.fl48.as_mut().unwrap();
            let (mut r, l) = f.finish(fw);
            r["closed"] = why.into();
            self.rec(r);
            self.line(l);
        }
    }
    /// rec(): an exit closes its fill's flow first; a realized record gets the compact flow
    pub(super) fn fl48_on_rec(&mut self, v: &mut serde_json::Value) {
        let Some(ev) = v["ev"].as_str() else { return };
        match ev {
            "presend_live_exit" => { if let Some(w) = v["w"].as_u64() { let s = self.sh.slot.load(Ordering::Relaxed); self.fl48_close(s, Some(w)); } }
            "presend_live_realized" => { if let Some(j) = v["w"].as_u64().and_then(|w| self.fl48.as_ref().and_then(|f| f.done.get(&w).cloned())) { v["flow"] = j; } }
            _ => {}
        }
    }
    pub(super) fn fl48_status(&self) -> String {
        self.fl48.as_ref().map_or(String::new(), |f| format!(" | FLOW LOG fills {} closed {} trades {} ({:.1} us each)", f.fills, f.closed, f.n_trades,
            if f.n_trades > 0 { f.ns.get() as f64 / f.n_trades as f64 / 1e3 } else { 0.0 }))
    }
}
