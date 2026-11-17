// dip51 DENSE FRONT: more tries per slot in a window's first slots, where most dips land (OFF by default = dip49c).
//
//   --presend-live-front SLOTS:K        a window's first SLOTS slots (1..10, counted from its first try) pace at K tries per slot
//                                       (K 1..50, >= --presend-live-k); after them the window paces at --presend-live-k as before
//   --presend-live-front-kinds KINDS    which windows: t2 | rearm | t2,rearm (default t2)
//
// Why (r92 wintrack, 1,280 dips): T2 dips come a median 556 ms after the trigger, 627 of 773 within 800 ms (best case +27.2 of
// +32.1 SOL); 158 dips had our tries landing before AND after with none inside, the dip open a median 5 ms against our ~20 ms
// spacing at 20 per slot. The engine refused K > 20; the total tries stay near dip49c's when the later slots pace lower (e.g.
// front 3:40 then k 10 = 190 tries per 10-slot T2 window against 200 at k 20).
//
// The rate caps are unchanged: a dense window still takes its tries from the global / per-lane buckets (refusals counted as before).
// Records: presend_live_arm / the re-arm's arm record carry "front": [slots, k] when the window paces dense; the start line says so.
use anyhow::{bail, Result};

// the flag names live in pslive.rs (D51FLAGS): the start-up flag check reads the known flags from that file's source
use super::D51FLAGS;

/// the most tries per slot a dense front may ask for
pub const FRONT_K_MAX: u64 = 50;
/// the most slots a dense front may last
pub const FRONT_SLOTS_MAX: u64 = 10;

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct D51Cfg {
    /// (slots, tries per slot) of the dense front; None = off (dip49c)
    pub front: Option<(u64, u64)>,
    pub t2: bool,
    pub rearm: bool,
}

impl D51Cfg {
    /// the flags (each validated; a value without its parent refused); `k` = --presend-live-k (the front may not be sparser)
    pub fn from_argv(argv: &[String], k: u64) -> Result<D51Cfg> {
        let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
        let arg = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned();
        let mut c = D51Cfg::default();
        match arg("--presend-live-front") {
            Some(s) if !s.starts_with("--") => {
                let bad = || anyhow::anyhow!("--presend-live-front SLOTS:K (SLOTS 1..{FRONT_SLOTS_MAX} = the window's first slots, K 1..{FRONT_K_MAX} tries per slot, >= --presend-live-k {k}), e.g. 3:40; got '{s}'");
                let (a, b) = s.split_once(':').ok_or_else(bad)?;
                let slots: u64 = a.parse().map_err(|_| bad())?;
                let kf: u64 = b.parse().map_err(|_| bad())?;
                if !(1..=FRONT_SLOTS_MAX).contains(&slots) || !(1..=FRONT_K_MAX).contains(&kf) || kf < k { return Err(bad()); }
                c.front = Some((slots, kf));
            }
            _ if has("--presend-live-front") => bail!("--presend-live-front needs a value (e.g. 3:40)"),
            _ => {}
        }
        match arg("--presend-live-front-kinds") {
            None if has("--presend-live-front-kinds") => bail!("--presend-live-front-kinds needs a value (t2 | rearm | t2,rearm)"),
            None => { c.t2 = true; }
            Some(s) => {
                if c.front.is_none() { bail!("--presend-live-front-kinds needs --presend-live-front SLOTS:K"); }
                for x in s.split(',') {
                    match x {
                        "t2" if !c.t2 => c.t2 = true,
                        "rearm" if !c.rearm => c.rearm = true,
                        _ => bail!("--presend-live-front-kinds {s}: t2 | rearm | t2,rearm (each once)"),
                    }
                }
            }
        }
        Ok(c)
    }

    /// the dense front for a window of this kind (None: paces at --presend-live-k all through, as dip49c)
    pub fn front_for(&self, rearm: bool) -> Option<(u64, u64)> {
        let on = if rearm { self.rearm } else { self.t2 };
        self.front.filter(|_| on)
    }

    /// the start line's part ("" when off)
    pub fn desc(&self) -> String {
        match self.front {
            None => String::new(),
            Some((s, k)) => format!(" | DIP51 DENSE FRONT: first {s} slot(s) of each {} window at {k} tries/slot, then --presend-live-k",
                match (self.t2, self.rearm) { (true, true) => "T2 and re-arm", (false, true) => "re-arm", _ => "T2" }),
        }
    }

    pub fn json(&self) -> serde_json::Value {
        match self.front {
            None => serde_json::Value::Null,
            Some((s, k)) => serde_json::json!({"slots": s, "k": k, "t2": self.t2, "rearm": self.rearm}),
        }
    }
}

/// a stray dip51 flag without --presend-live is refused
pub fn needs_presend_live(argv: &[String]) -> Result<()> {
    let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
    if !has("--presend-live") { if let Some(f) = D51FLAGS.iter().find(|f| has(f)) { bail!("{f} needs --presend-live"); } }
    Ok(())
}
