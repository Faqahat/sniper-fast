// =====================================================================================================================
// dip37 FEE A/B (owner 11-04: approved to BUILD, not to release): a PER-ARM priority-fee A/B on the pre-send live path.
// Why: our pre-sent buys pay CU price 1,000 uL x CU limit 120k (~120 lamports of priority) + a 100k-lamport tip; the rival pre-send
// bots 4ggJqUDD / DL7cmioG pay 17-20k uL. Leaders that order by fee (BAM, Harmonic, Firedancer, Agave) sort them ahead of us in the
// same slot; on Jito leaders the tip auction decides (we already win there).
//   --presend-live-fee-ab on|off (off)       each window gets arm A or B ONCE, at its arm (T2 and re-arm alike)
//   --presend-live-ab-cu-price-micro N        arm B's CU price (needed with the A/B on; <= 1,000,000 as A's)
//   --presend-live-ab-cu-limit N              arm B's CU limit (default: arm A's --presend-live-cu-limit; 20000..400000)
//   --presend-live-ab-tip-lamports N          arm B's tip (default: arm A's = --presend-live-tip-lamports, else the path's own; <= 0.01 SOL,
//                                             >= every attempt path's minimum tip)
//   --presend-live-ab-clients LIST            the leader clients (gossip clientId, as lat::leader_of gives it) where arm B's values apply:
//                                             default AgaveBam,HarmonicAgave,HarmonicFiredancer,Firedancer,Agave (NOT JitoLabs). On any
//                                             other leader (Jito, an unknown one) an arm-B attempt is signed with arm A's values
//   --presend-live-ab-split arm|hour (arm)    arm: the window id's parity (even A, odd B; T2 and re-arm share the id counter);
//                                             hour: the UTC hour's parity at the arm (even A, odd B)
// Per attempt: its window's arm, then the client rule from THAT attempt's target leader (lat::leader_of(slot): the slot it is signed
// for), then CU limit / CU price / tip from those, then signed. The pre-send path has ONE build site (the sender's att_ixs_fee, one fresh
// signature per attempt on a recent blockhash): no pre-signed or durable-nonce variant of an attempt exists (--nonce-fanout is the reactive
// buys' only).
// Records, ONLY with the A/B on: presend_attempt / presend_attempt_land / presend_live_fill / presend_live_realized / presend_live_arm get
// fee_arm ("A" / "B"), fee_grp ("fee" = a listed client, "jito" = JitoLabs, "other"), fee_b (B's values used), cu_price, cu_limit, tip;
// a landed try's record (ok / 6042) gets "slot_tr" (every trade of the mint in its landing slot: [idx, j, user, buy], full addresses:
// the rivals' in-slot order for feeab_report.py); run_end presend_live.fee_ab (per arm and per arm x group: attempts, failed tries and
// their fees, fills, fills per 1k attempts, realized); the status line " | FEE A/B ...". OFF: nothing of it runs (dip36 byte for byte).
// =====================================================================================================================
use super::*;

/// the default B clients (fee-ordered leaders; never JitoLabs)
pub const AB_CLIENTS: &str = "AgaveBam,HarmonicAgave,HarmonicFiredancer,Firedancer,Agave";
/// the gossip clientIds the engine knows (src/leaders.rs); "Unknown(N)" is accepted too
pub const KNOWN_CLIENTS: [&str; 10] = ["Agave", "AgaveBam", "FireBAM", "Firedancer", "Frankendancer", "HarmonicAgave", "HarmonicFiredancer", "JitoLabs", "Rakurai", "Raiku"];
pub const ARMS: [&str; 2] = ["A", "B"];
/// leader groups: 0 a listed (B) client, 1 JitoLabs, 2 any other
pub const GRPS: [&str; 3] = ["fee", "jito", "other"];
/// the "slot_tr" list's cap per landed try
pub const SLOT_TR_MAX: usize = 32;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Split { Arm, Hour }

/// the A/B's parameters (off by default: nothing of it runs)
#[derive(Clone, Debug, PartialEq)]
pub struct FeeAbCfg {
    pub on: bool,
    pub split: Split,
    /// arm B's CU price (uL)
    pub cu_price: u64,
    /// arm B's CU limit (None: arm A's)
    pub cu_limit: Option<u32>,
    /// arm B's tip (None: arm A's)
    pub tip: Option<u64>,
    /// where arm B's values apply
    pub clients: Vec<String>,
}

impl Default for FeeAbCfg {
    fn default() -> FeeAbCfg { FeeAbCfg { on: false, split: Split::Arm, cu_price: 0, cu_limit: None, tip: None, clients: AB_CLIENTS.split(',').map(String::from).collect() } }
}

/// --presend-live-ab-clients LIST: comma-separated known clientIds (or Unknown(N)), no duplicates
pub fn clients_parse(s: &str) -> Result<Vec<String>> {
    let mut v: Vec<String> = Vec::new();
    for c in s.split(',').map(str::trim) {
        if c.is_empty() { bail!("--presend-live-ab-clients '{s}': an empty name (comma-separated clientIds, e.g. {AB_CLIENTS})"); }
        let unk = c.strip_prefix("Unknown(").and_then(|x| x.strip_suffix(')')).is_some_and(|n| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit()));
        if !KNOWN_CLIENTS.contains(&c) && !unk { bail!("--presend-live-ab-clients: '{c}' is not a leader client the engine knows ({} or Unknown(N))", KNOWN_CLIENTS.join(", ")); }
        if v.iter().any(|x| x == c) { bail!("--presend-live-ab-clients: '{c}' twice"); }
        v.push(c.to_string());
    }
    Ok(v)
}

impl FeeAbCfg {
    /// the ranges (arm A's own are Cfg::check's)
    pub fn check(&self) -> Result<()> {
        if !self.on { return Ok(()); }
        if self.cu_price > 1_000_000 { bail!("--presend-live-ab-cu-price-micro above 1,000,000 (a failed attempt would cost > 0.0001 SOL in priority): refusing"); }
        if self.cu_limit.is_some_and(|l| !(20_000..=400_000).contains(&l)) { bail!("--presend-live-ab-cu-limit must be 20000..400000"); }
        if self.tip.is_some_and(|t| t > 10_000_000) { bail!("--presend-live-ab-tip-lamports above 0.01 SOL: refusing"); }
        if self.clients.is_empty() { bail!("--presend-live-ab-clients: no client"); }
        Ok(())
    }

    /// a window's arm at its arm (0 = A, 1 = B): `id` its window id, `now_ns` the wall clock (unix ns)
    pub fn assign(&self, id: u64, now_ns: u64) -> u8 {
        match self.split { Split::Arm => (id & 1) as u8, Split::Hour => ((now_ns / 3_600_000_000_000) & 1) as u8 }
    }
    /// arm B's values apply on this leader client
    pub fn applies(&self, client: &str) -> bool { self.clients.iter().any(|c| c == client) }
    /// the leader group of a client (GRPS)
    pub fn grp(&self, client: &str) -> u8 { if self.applies(client) { 0 } else if client == "JitoLabs" { 1 } else { 2 } }

    /// run_start's presend_live.fee_ab (arm A = the run's own values)
    pub fn json(&self, a_limit: u32, a_price: u64, a_tip: Option<u64>) -> serde_json::Value {
        serde_json::json!({"on": self.on, "split": match self.split { Split::Arm => "arm", Split::Hour => "hour" }, "clients": self.clients,
            "a": {"cu_price": a_price, "cu_limit": a_limit, "tip": a_tip},
            "b": {"cu_price": self.cu_price, "cu_limit": self.cu_limit.unwrap_or(a_limit), "tip": self.tip.or(a_tip)}})
    }

    /// the start line's part
    pub fn desc(&self, a_limit: u32, a_price: u64, a_tip: Option<u64>) -> String {
        let tip = |t: Option<u64>| t.map_or("the path's".to_string(), |x| x.to_string());
        format!("FEE A/B ON (split {}): A = {} uL x {} CU, tip {} | B = {} uL x {} CU, tip {} on leaders {} (any other leader: A's values) | failed try A {} / B {} lamports",
            match self.split { Split::Arm => "window id parity: even A, odd B", Split::Hour => "UTC hour parity at the arm: even A, odd B" },
            a_price, a_limit, tip(a_tip), self.cu_price, self.cu_limit.unwrap_or(a_limit), tip(self.tip.or(a_tip)), self.clients.join(","),
            fail_fee(a_limit, a_price), fail_fee(self.cu_limit.unwrap_or(a_limit), self.cu_price))
    }
}

/// a failed attempt's fee: 5,000 base + CU limit x price (the priority fee is charged on the limit; Cfg::fail_fee's formula)
pub fn fail_fee(cu_limit: u32, cu_price: u64) -> u64 { 5_000 + (cu_limit as u64 * cu_price).div_ceil(1_000_000) }

/// one attempt's fee values (only with the A/B on)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AttFee {
    /// its window's arm (0 A, 1 B), its leader's group (GRPS)
    pub arm: u8, pub grp: u8,
    /// arm B's values were used (arm B on a listed client)
    pub b: bool,
    pub cu_limit: u32, pub cu_price: u64,
}

impl AttFee {
    pub fn fail_fee(&self) -> u64 { fail_fee(self.cu_limit, self.cu_price) }
    /// the record fields (`tip`: the attempt's tip lamports, 0 = none)
    pub fn put(&self, j: &mut serde_json::Value, tip: u64) {
        j["fee_arm"] = ARMS[self.arm as usize].into();
        j["fee_grp"] = GRPS[self.grp as usize].into();
        j["fee_b"] = self.b.into();
        j["cu_price"] = self.cu_price.into();
        j["cu_limit"] = self.cu_limit.into();
        j["tip"] = tip.into();
    }
}

/// An attempt's (CU limit, CU price, tip) and its A/B values (pure: unit-tested). `arm`: its window's arm (None: the A/B is off);
/// `client`: the attempt's target leader's clientId; `path_tip`: the path's tip account and its own lamports (None: a tipless path).
/// OFF (arm None or the A/B off): exactly dip36's (cfg.cu_limit, cfg.cu_price, the path's tip with --presend-live-tip-lamports over it)
pub fn att_fee(cfg: &Cfg, arm: Option<u8>, client: &str, path_tip: Option<(Pk, u64)>) -> (u32, u64, Option<(Pk, u64)>, Option<AttFee>) {
    let a_tip = path_tip.map(|(a, l)| (a, cfg.tip.unwrap_or(l)));
    let Some(arm) = arm.filter(|_| cfg.fab.on) else { return (cfg.cu_limit, cfg.cu_price, a_tip, None) };
    let f = &cfg.fab;
    let b = arm == 1 && f.applies(client);
    let (lim, price, tip) = if b { (f.cu_limit.unwrap_or(cfg.cu_limit), f.cu_price, path_tip.map(|(a, l)| (a, f.tip.unwrap_or(cfg.tip.unwrap_or(l))))) }
        else { (cfg.cu_limit, cfg.cu_price, a_tip) };
    (lim, price, tip, Some(AttFee { arm, grp: f.grp(client), b, cu_limit: lim, cu_price: price }))
}

/// one arm x group's counters (the main loop's)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Cell {
    /// attempts registered (sent)
    pub att: u64,
    /// attempts that landed failed (their fees), attempts resolved unseen
    pub fail: u64, pub fail_fee: u64, pub unseen: u64,
    /// fills, their tx fees and tips
    pub fills: u64, pub fill_fee: u64, pub tips: u64,
}

/// the realized P&L per arm x group (pnl lamports, positions, wins): the async realized lookups add to it
#[derive(Default, Debug)]
pub struct Rz(Mutex<[[(i64, u64, u64); 3]; 2]>);
impl Rz {
    pub fn add(&self, arm: u8, grp: u8, pnl: i64) {
        let mut g = self.0.lock().unwrap_or_else(|e| e.into_inner());
        let c = &mut g[(arm as usize).min(1)][(grp as usize).min(2)];
        c.0 += pnl; c.1 += 1; if pnl > 0 { c.2 += 1; }
    }
    pub fn get(&self) -> [[(i64, u64, u64); 3]; 2] { *self.0.lock().unwrap_or_else(|e| e.into_inner()) }
}

/// a position's A/B tag for its realized lookup: its window's arm, the filling attempt's group / values (None: an orphan, no attempt)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RzAb { pub arm: u8, pub grp: u8, pub fee: Option<AttFee>, pub tip: u64 }
impl RzAb {
    pub fn put(&self, j: &mut serde_json::Value) {
        match &self.fee {
            Some(f) => f.put(j, self.tip),
            None => { j["fee_arm"] = ARMS[self.arm as usize].into(); j["fee_grp"] = GRPS[self.grp as usize].into(); }
        }
    }
}

/// the A/B's state in the probe (None: off)
#[derive(Debug, Default)]
pub struct FabSt {
    /// [arm][group]
    pub c: [[Cell; 3]; 2],
    /// windows armed per arm
    pub armed: [u64; 2],
    /// every window's arm (window id -> arm): an orphan position's realized lookup, the fills of late attempts
    pub wins: FxHashMap<u64, u8>,
    pub rz: Arc<Rz>,
}

impl FabSt {
    pub fn cell(&mut self, f: &AttFee) -> &mut Cell { &mut self.c[(f.arm as usize).min(1)][(f.grp as usize).min(2)] }
    pub fn arm_of(&self, w: u64) -> Option<u8> { self.wins.get(&w).copied() }

    /// an arm's totals over the groups
    pub fn arm_tot(&self, a: usize) -> Cell {
        let mut t = Cell::default();
        for c in &self.c[a] { t.att += c.att; t.fail += c.fail; t.fail_fee += c.fail_fee; t.unseen += c.unseen; t.fills += c.fills; t.fill_fee += c.fill_fee; t.tips += c.tips; }
        t
    }

    /// the status line's part
    pub fn status(&self) -> String {
        let rz = self.rz.get();
        let part = |a: usize| {
            let t = self.arm_tot(a);
            let (pnl, n, _) = rz[a].iter().fold((0i64, 0u64, 0u64), |s, x| (s.0 + x.0, s.1 + x.1, s.2 + x.2));
            let by: Vec<String> = (0..3).filter(|&g| self.c[a][g].att > 0).map(|g| format!("{} {}/{}", GRPS[g], self.c[a][g].fills, self.c[a][g].att)).collect();
            format!("{}: windows {} attempts {} failed {} (fees {:.6} SOL) fills {} ({:.2}/1k) realized {:+.4} SOL ({n}) [fills/attempts {}]", ARMS[a], self.armed[a], t.att, t.fail,
                t.fail_fee as f64 / 1e9, t.fills, per_1k(t.fills, t.att), pnl as f64 / 1e9, by.join(", "))
        };
        format!(" | FEE A/B {} | {}", part(0), part(1))
    }

    /// run_end's totals (the realized part is completed once the realized lookups are in: `realized_json`)
    pub fn json(&self) -> serde_json::Value {
        let cell = |c: &Cell| serde_json::json!({"attempts": c.att, "failed": c.fail, "failed_fees": c.fail_fee, "unseen": c.unseen, "fills": c.fills,
            "fill_fees": c.fill_fee, "tips": c.tips, "fills_per_1k": per_1k(c.fills, c.att)});
        let mut j = serde_json::Map::new();
        for a in 0..2 {
            let mut x = cell(&self.arm_tot(a));
            x["windows"] = self.armed[a].into();
            for g in 0..3 { x["by_grp"][GRPS[g]] = cell(&self.c[a][g]); }
            j.insert(ARMS[a].to_string(), x);
        }
        let mut v = serde_json::Value::Object(j);
        v["realized"] = self.realized_json();
        v
    }

    /// the realized P&L per arm (and per arm x group) so far
    pub fn realized_json(&self) -> serde_json::Value {
        let rz = self.rz.get();
        let mut j = serde_json::Map::new();
        for a in 0..2 {
            let (pnl, n, w) = rz[a].iter().fold((0i64, 0u64, 0u64), |s, x| (s.0 + x.0, s.1 + x.1, s.2 + x.2));
            let mut x = serde_json::json!({"pnl": pnl, "n": n, "wins": w});
            for g in 0..3 { x["by_grp"][GRPS[g]] = serde_json::json!({"pnl": rz[a][g].0, "n": rz[a][g].1, "wins": rz[a][g].2}); }
            j.insert(ARMS[a].to_string(), x);
        }
        serde_json::Value::Object(j)
    }

    /// the run end's summary line (per arm: attempts, failed tries and fees, fills, fills per 1k, realized)
    pub fn end_line(&self) -> String {
        let rz = self.rz.get();
        let mut s = String::from("=== DIP PRESEND LIVE FEE A/B:");
        for a in 0..2 {
            let t = self.arm_tot(a);
            let (pnl, n, w) = rz[a].iter().fold((0i64, 0u64, 0u64), |s, x| (s.0 + x.0, s.1 + x.1, s.2 + x.2));
            s += &format!(" | {}: windows {} attempts {} failed {} (fees {:.6} SOL) fills {} ({:.2} per 1k attempts) realized {:+.6} SOL ({} positions, {} won), net of failed fees {:+.6} SOL",
                ARMS[a], self.armed[a], t.att, t.fail, t.fail_fee as f64 / 1e9, t.fills, per_1k(t.fills, t.att), pnl as f64 / 1e9, n, w, (pnl - t.fail_fee as i64) as f64 / 1e9);
        }
        s
    }
}

/// a landed try's "slot_tr": the mint's trades in its landing slot `slot` (the tape sorted by chain position), as [idx, j, user, buy]:
/// the SLOT_TR_MAX / 2 nearest before our tx index `idx` and the SLOT_TR_MAX / 2 nearest at or after it (pure: unit-tested)
pub fn slot_tr(tape: &[&pl::Trade], slot: u64, idx: u32) -> Vec<serde_json::Value> {
    let h = SLOT_TR_MAX / 2;
    let inslot: Vec<&pl::Trade> = tape.iter().copied().filter(|t| t.s == slot).collect();
    let k = inslot.iter().position(|t| t.i >= idx).unwrap_or(inslot.len());
    inslot[k.saturating_sub(h)..(k + h).min(inslot.len())].iter().map(|t| serde_json::json!([t.i, t.j, b58(&t.user), t.buy])).collect()
}

/// fills per 1,000 attempts (0 without attempts)
pub fn per_1k(fills: u64, att: u64) -> f64 { if att == 0 { 0.0 } else { fills as f64 * 1000.0 / att as f64 } }
