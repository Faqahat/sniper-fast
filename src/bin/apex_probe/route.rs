//! Leader book + per-leader-client routing: the dip engine's `lat` module (snipe_engine.rs, LAT 2026-10-19) re-done for the
//! probe: the create slot's leader client picks the send paths (`--routes`), plus the next leader's paths when the create
//! is in its leader's last slot (not for Harmonic leaders: --no-union-harmonic, as the dip engine runs).

use crate::logic;
use anyhow::{bail, Context, Result};
use arbx::rpc;
use arbx::send;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};
use std::time::Duration;

pub struct Book { base: u64, idx: Vec<u32>, names: Vec<String>, client: HashMap<String, String> }

pub static BOOK: RwLock<Option<Book>> = RwLock::new(None);

/// (leader, clientId) of `slot` from the cached book (no network)
pub fn leader_of(slot: u64) -> Option<(String, String)> {
    let g = BOOK.read().unwrap();
    let b = g.as_ref()?;
    let i = *b.idx.get(slot.checked_sub(b.base)? as usize)?;
    if i == u32::MAX { return None; }
    let l = b.names.get(i as usize)?.clone();
    let c = b.client.get(&l).cloned().unwrap_or_default();
    Some((l, c))
}

/// leader schedule (current + next epoch, one u32 per slot) + every node's clientId
pub async fn refresh(rpc: &rpc::Rpc) -> Result<String> {
    let ei = rpc.call("getEpochInfo", serde_json::json!([])).await.context("getEpochInfo")?;
    let start = ei["absoluteSlot"].as_u64().unwrap_or(0).saturating_sub(ei["slotIndex"].as_u64().unwrap_or(0));
    let len = ei["slotsInEpoch"].as_u64().unwrap_or(432_000) as usize;
    let mut names: Vec<String> = Vec::new();
    let mut pos: HashMap<String, u32> = HashMap::new();
    let mut idx = vec![u32::MAX; 2 * len];
    for (k, a) in [(0usize, serde_json::Value::Null), (1usize, serde_json::json!(start + len as u64))] {
        let Ok(ls) = rpc.call("getLeaderSchedule", serde_json::json!([a])).await else { continue };
        let Some(obj) = ls.as_object() else { continue };
        for (leader, slots) in obj {
            let id = *pos.entry(leader.clone()).or_insert_with(|| { names.push(leader.clone()); (names.len() - 1) as u32 });
            for s in slots.as_array().into_iter().flatten().filter_map(|x| x.as_u64()) {
                let j = k * len + s as usize;
                if j < idx.len() { idx[j] = id; }
            }
        }
    }
    let mapped = idx.iter().filter(|x| **x != u32::MAX).count();
    if mapped == 0 { bail!("getLeaderSchedule returned nothing"); }
    let cn = rpc.call("getClusterNodes", serde_json::json!([])).await.context("getClusterNodes")?;
    let mut client = HashMap::new();
    for n in cn.as_array().into_iter().flatten() {
        if let (Some(p), Some(c)) = (n["pubkey"].as_str(), n["clientId"].as_str()) { client.insert(p.to_string(), c.to_string()); }
    }
    let msg = format!("LEADER-BOOK epoch_start={start} slots_mapped={mapped} leaders={} nodes_with_client={}", names.len(), client.len());
    let mut g = BOOK.write().unwrap();
    if client.is_empty() { if let Some(old) = g.as_ref() { client = old.client.clone(); } }
    *g = Some(Book { base: start, idx, names, client });
    Ok(msg)
}

pub fn start_refresh(rpc: Arc<rpc::Rpc>, stop: Arc<AtomicBool>) {
    tokio::spawn(async move {
        let mut wait = Duration::from_secs(600);
        while !stop.load(Ordering::Relaxed) {
            tokio::time::sleep(wait).await;
            match refresh(&rpc).await {
                Ok(m) => { eprintln!("  {m}"); wait = Duration::from_secs(600); }
                Err(e) => { eprintln!("  LEADER-BOOK refresh failed (kept the old one, retry in 60 s): {e:#}"); wait = Duration::from_secs(60); }
            }
        }
    });
}

/// a lane resolved against the built paths
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LaneIdx { pub pi: usize, pub tip: Option<u64>, pub prio: Option<u64> }

/// The lanes (per leader class) resolved against the built paths
pub struct Routes {
    pub map: HashMap<String, Vec<LaneIdx>>,
    pub paths: Vec<Arc<send::Path>>,
    pub no_union_harmonic: bool,
}

/// Route metadata of one buy (logged)
#[derive(Clone, Debug, Default, serde::Serialize)]
pub struct Meta { pub route: String, pub leader: String, pub client: String, pub class: String }

impl Routes {
    /// lane names -> path indices. A lane whose path is not built is dropped (named in the notes); a class left empty falls
    /// back to default; an empty default is an error.
    pub fn resolve(spec: &HashMap<String, Vec<logic::LaneSpec>>, paths: Vec<Arc<send::Path>>, no_union_harmonic: bool) -> Result<(Routes, Vec<String>)> {
        let mut notes = Vec::new();
        let mut map = HashMap::new();
        for (c, lanes) in spec {
            let mut v = Vec::new();
            for l in lanes {
                match paths.iter().position(|p| p.name == l.path) {
                    Some(i) => v.push(LaneIdx { pi: i, tip: l.tip, prio: l.prio }),
                    None => notes.push(format!("lane {c}: path '{}' is not built (missing from the config, disabled, or its key failed): left out", l.path)),
                }
            }
            if !v.is_empty() { map.insert(c.clone(), v); } else if c != "default" { notes.push(format!("lane {c}: no path left: uses default")); }
        }
        if !map.contains_key("default") { bail!("the default lane set has no usable path"); }
        Ok((Routes { map, paths, no_union_harmonic }, notes))
    }

    /// the lanes for a create in `slot` (its leader's class, + the next leader's when the slot is its leader's last)
    pub fn fan(&self, slot: u64) -> (Vec<LaneIdx>, Meta) {
        let mut meta = Meta::default();
        let l0 = leader_of(slot);
        let c0 = l0.as_ref().map(|(_, c)| logic::class(c));
        if let Some((l, c)) = &l0 { meta.leader = l.clone(); meta.client = c.clone(); }
        meta.class = c0.unwrap_or("unknown").to_string();
        let next = match (&l0, leader_of(slot + 1)) { (Some((a, _)), Some((b, c1))) if *a != b => Some(logic::class(&c1)), _ => None };
        let mut classes = logic::route_classes(c0, next, self.no_union_harmonic);
        let mut v: Vec<LaneIdx> = Vec::new();
        for c in &classes {
            for l in self.map.get(*c).or_else(|| self.map.get("default")).into_iter().flatten() { if !v.iter().any(|x| x.pi == l.pi) { v.push(*l); } }
        }
        if v.is_empty() { v = self.map["default"].clone(); classes.push("default"); }
        meta.route = format!("route:{}", classes.join("+"));
        (v, meta)
    }

    pub fn describe(&self) -> Vec<String> {
        let mut ks: Vec<_> = self.map.keys().cloned().collect();
        ks.sort();
        ks.iter().map(|c| format!("LANES {c:8} -> {}", self.map[c].iter().map(|l| format!("{}{}{}", self.paths[l.pi].name,
            l.tip.map(|t| format!(":{t}")).unwrap_or_default(), l.prio.map(|p| format!("@{p}")).unwrap_or_default())).collect::<Vec<_>>().join(" + "))).collect()
    }
}
