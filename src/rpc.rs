//! Minimal JSON-RPC client (off the hot path): account snapshots at boot, lookup tables, slot/blockhash, signature
//! statuses and transaction simulation.
//!
//! WP-02 (runtime split): `Rpc::bind` ties a client to the background runtime: every call is spawned there, whichever
//! runtime awaits it, and replies over `runtime::LARGE_REPLY` bytes are parsed in `spawn_blocking`. The HTTP work
//! checks it is not on an `arbx-hot` thread (`runtime::check_not_hot`).
use crate::tx::{b58, Pk};
use anyhow::{bail, Context, Result};
use base64::Engine as _;
use serde_json::{json, Value};

/// One RPC provider. `bearer` is sent as `Authorization: Bearer <value>` (Haan); keys in the URL need nothing.
#[derive(Debug, Clone)]
pub struct Endpoint { pub name: String, pub url: String, pub bearer: Option<String> }

/// Per-provider results: every call goes to every provider at once, the first good answer is used, and every
/// provider's own latency is still recorded (so each call measures all of them).
#[derive(Default)]
pub struct Stats {
    /// (provider, method) -> latencies (µs) of successful answers
    pub lat: std::collections::BTreeMap<(String, String), Vec<u64>>,
    pub wins: std::collections::BTreeMap<String, u64>,
    pub errors: std::collections::BTreeMap<String, u64>,
    /// (provider, reason) -> count; reasons have URLs cut to their host so no key is ever logged
    pub why: std::collections::BTreeMap<(String, String), u64>,
    pub calls: u64,
}

/// An error message with every URL reduced to scheme://host (provider keys live in paths and query strings).
pub fn scrub(msg: &str) -> String {
    let mut out = String::with_capacity(msg.len());
    let mut rest = msg;
    while let Some(i) = rest.find("http") {
        out.push_str(&rest[..i]);
        let url = &rest[i..];
        let end = url.find(|c: char| c.is_whitespace() || c == ')' || c == '"' || c == '\'').unwrap_or(url.len());
        let u = &url[..end];
        let host_end = u.find("://").map(|p| p + 3).and_then(|p| u[p..].find(|c| c == '/' || c == '?').map(|q| p + q)).unwrap_or(u.len());
        out.push_str(&u[..host_end]);
        rest = &url[end..];
    }
    out.push_str(rest);
    // anything still looking like a key parameter
    for k in ["api-key=", "api_key=", "apikey=", "token="] {
        while let Some(i) = out.find(k) { let j = out[i..].find(|c: char| c == '&' || c.is_whitespace()).map_or(out.len(), |x| i + x); out.replace_range(i + k.len()..j, "…"); break; }
    }
    out
}

#[derive(Clone)]
pub struct Rpc { eps: std::sync::Arc<Vec<Endpoint>>, http: reqwest::Client, pub stats: std::sync::Arc<std::sync::Mutex<Stats>>,
    /// try the providers in order, the next only if one fails (a race sends every call to all of them: every call costs
    /// rate limit everywhere, and 15% of calls then failed on all of them)
    failover: bool,
    /// the runtime every call runs on (`bind`; `arbx run`: rt_bg). None: the caller's
    rt: Option<tokio::runtime::Handle> }

#[derive(Debug, Clone)]
pub struct Account { pub owner: Pk, pub lamports: u64, pub data: Vec<u8> }

impl Rpc {
    pub fn new(url: String) -> Rpc { Rpc::race(vec![Endpoint { name: "rpc".into(), url, bearer: None }]) }

    pub fn race(eps: Vec<Endpoint>) -> Rpc {
        let http = reqwest::Client::builder().tcp_nodelay(true).pool_idle_timeout(std::time::Duration::from_secs(90))
            .pool_max_idle_per_host(8).timeout(std::time::Duration::from_secs(20)).build().expect("http client");
        Rpc { eps: std::sync::Arc::new(eps), http, stats: Default::default(), failover: false, rt: None }
    }
    pub fn with_failover(mut self, on: bool) -> Rpc { self.failover = on; self }

    /// Run every call of this client (and of the clients `only` makes from it) on `rt` (the background runtime)
    pub fn bind(mut self, rt: tokio::runtime::Handle) -> Rpc { self.rt = Some(rt); self }
    pub fn is_bound(&self) -> bool { self.rt.is_some() }

    pub fn names(&self) -> Vec<String> { self.eps.iter().map(|e| e.name.clone()).collect() }

    /// a client on only the named providers (one provider, not the race, for simulations and settlement)
    /// the named providers, in the order named (the failover order)
    pub fn only(&self, names: &[String]) -> Rpc {
        Rpc { eps: std::sync::Arc::new(names.iter().filter_map(|n| self.eps.iter().find(|e| &e.name == n).cloned()).collect()), http: self.http.clone(),
              stats: Default::default(), failover: self.failover, rt: self.rt.clone() }
    }
    pub fn is_empty(&self) -> bool { self.eps.is_empty() }

    async fn one(http: &reqwest::Client, ep: &Endpoint, body: &Value, method: &str, retry: bool) -> Result<Value> {
        crate::runtime::check_not_hot("an RPC call");
        let mut wait = 300u64;
        for attempt in 0..8 {
            let mut req = http.post(&ep.url).json(body);
            if let Some(b) = &ep.bearer { req = req.header("authorization", format!("Bearer {b}")); }
            let resp = req.send().await.with_context(|| format!("{} {method}", ep.name))?;
            let status = resp.status();
            let limited = status.as_u16() == 429;
            let r: Value = if limited { Value::Null } else {
                let bytes = resp.bytes().await.with_context(|| format!("{} {method}: reading reply", ep.name))?;
                match parse_reply(bytes.clone()).await {
                    Ok(v) => v,
                    Err(_) => {
                        let text = String::from_utf8_lossy(&bytes);
                        let snippet: String = text.chars().take(120).map(|c| if c.is_control() { ' ' } else { c }).collect();
                        bail!("{} {method}: HTTP {} with a non-JSON reply ({} bytes): {:?}", ep.name, status.as_u16(), bytes.len(), snippet.trim());
                    }
                }
            };
            let limited = limited || r["error"]["code"].as_i64() == Some(429);
            if limited && retry && attempt < 7 { tokio::time::sleep(std::time::Duration::from_millis(wait)).await; wait = (wait * 2).min(5_000); continue; }
            if limited { bail!("{} {method}: rate limited", ep.name); }
            if let Some(e) = r.get("error") { bail!("{} {method}: {e}", ep.name); }
            // a reply with neither a result nor an error (a gateway's own message) is not an answer: it must not win the race
            match r.get("result") {
                Some(v) => return Ok(v.clone()),
                None => bail!("{} {method}: no result in reply: {}", ep.name, r.to_string().chars().take(120).collect::<String>()),
            }
        }
        bail!("{} {method}: still rate limited", ep.name)
    }

    /// One JSON-RPC call raced across every provider (or in failover order); returns the first successful result. A
    /// bound client runs it on its runtime (`bind`)
    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        match &self.rt {
            Some(h) => {
                let mut me = self.clone();
                me.rt = None;
                let m = method.to_string();
                h.spawn(async move { me.call_here(&m, params).await }).await.map_err(|e| anyhow::anyhow!("rpc {method}: task failed: {e}"))?
            }
            None => self.call_here(method, params).await,
        }
    }

    async fn call_here(&self, method: &str, params: Value) -> Result<Value> {
        let body = std::sync::Arc::new(json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params }));
        if self.failover {
            self.stats.lock().unwrap().calls += 1;
            let mut last = None;
            for (k, ep) in self.eps.iter().enumerate() {
                let t0 = std::time::Instant::now();
                let r = match tokio::time::timeout(std::time::Duration::from_secs(3), Rpc::one(&self.http, ep, &body, method, k + 1 == self.eps.len())).await {
                    Ok(r) => r,
                    Err(_) => Err(anyhow::anyhow!("{} {method}: no answer in 3 s", ep.name)),
                };
                let mut s = self.stats.lock().unwrap();
                match r {
                    Ok(v) => { s.lat.entry((ep.name.clone(), method.to_string())).or_default().push(t0.elapsed().as_micros() as u64); *s.wins.entry(ep.name.clone()).or_default() += 1; return Ok(v); }
                    Err(e) => {
                        *s.errors.entry(ep.name.clone()).or_default() += 1;
                        let mut why = scrub(&format!("{e:#}")); why.truncate(200);
                        *s.why.entry((ep.name.clone(), why)).or_default() += 1;
                        last = Some(e);
                    }
                }
            }
            return Err(last.unwrap_or_else(|| anyhow::anyhow!("rpc {method}: no providers")));
        }
        let (tx, mut rx) = tokio::sync::mpsc::channel::<(String, Result<Value>)>(self.eps.len().max(1));
        let solo = self.eps.len() == 1;
        for ep in self.eps.iter().cloned() {
            let (http, body, tx, stats, m) = (self.http.clone(), body.clone(), tx.clone(), self.stats.clone(), method.to_string());
            tokio::spawn(async move {
                let t0 = std::time::Instant::now();
                let r = Rpc::one(&http, &ep, &body, &m, solo).await;
                let us = t0.elapsed().as_micros() as u64;
                {
                    let mut s = stats.lock().unwrap();
                    match &r {
                        Ok(_) => s.lat.entry((ep.name.clone(), m.clone())).or_default().push(us),
                        Err(e) => {
                            *s.errors.entry(ep.name.clone()).or_default() += 1;
                            let mut why = scrub(&format!("{e:#}"));
                            why.truncate(200);
                            *s.why.entry((ep.name.clone(), why)).or_default() += 1;
                        }
                    }
                }
                let _ = tx.send((ep.name, r)).await;
            });
        }
        drop(tx);
        self.stats.lock().unwrap().calls += 1;
        let mut last = None;
        while let Some((name, r)) = rx.recv().await {
            match r {
                Ok(v) => { *self.stats.lock().unwrap().wins.entry(name).or_default() += 1; return Ok(v); }
                Err(e) => last = Some(e),
            }
        }
        Err(last.unwrap_or_else(|| anyhow::anyhow!("rpc {method}: no providers")))
    }

    /// the most common failure reasons per provider
    pub fn reasons(&self, per: usize) -> Vec<String> {
        let s = self.stats.lock().unwrap();
        let mut v: Vec<(&(String, String), &u64)> = s.why.iter().collect();
        v.sort_by(|a, b| a.0 .0.cmp(&b.0 .0).then(b.1.cmp(a.1)));
        let mut out = Vec::new();
        let mut last = String::new();
        let mut n = 0;
        for ((ep, why), c) in v {
            if *ep != last { last = ep.clone(); n = 0; }
            n += 1;
            if n <= per { out.push(format!("{ep}: {c} x {why}")); }
        }
        out
    }

    /// one line per provider: wins, errors, p50/p90 latency per method
    pub fn summary(&self) -> Vec<String> {
        let mut s = self.stats.lock().unwrap();
        let calls = s.calls.max(1);
        let names: Vec<String> = self.eps.iter().map(|e| e.name.clone()).collect();
        let mut out = Vec::new();
        for n in names {
            let wins = s.wins.get(&n).copied().unwrap_or(0);
            let errs = s.errors.get(&n).copied().unwrap_or(0);
            let mut parts = Vec::new();
            for ((ep, m), v) in s.lat.iter_mut() {
                if *ep != n || v.is_empty() { continue; }
                v.sort_unstable();
                let p = |q: f64| v[((v.len() - 1) as f64 * q).round() as usize] as f64 / 1000.0;
                parts.push(format!("{m} {:.1}/{:.1} ms ({})", p(0.5), p(0.9), v.len()));
            }
            out.push(format!("{n}: first {wins}/{calls} ({:.0}%), errors {errs}; {}", wins as f64 * 100.0 / calls as f64, parts.join(", ")));
        }
        out
    }

    /// getMultipleAccounts in batches of 100, processed commitment; returns (slot, accounts in order)
    pub async fn accounts(&self, keys: &[Pk]) -> Result<(u64, Vec<Option<Account>>)> {
        let mut out = Vec::with_capacity(keys.len());
        let mut slot = 0;
        for chunk in keys.chunks(100) {
            let ks: Vec<String> = chunk.iter().map(b58).collect();
            let r = self.call("getMultipleAccounts", json!([ks, { "encoding": "base64", "commitment": "processed" }])).await?;
            slot = slot.max(r["context"]["slot"].as_u64().unwrap_or(0));
            for v in r["value"].as_array().context("getMultipleAccounts: no value")? {
                out.push(parse_account(v));
            }
            // pace bulk fetches (public endpoints allow a few requests per second)
            if keys.len() > 100 { tokio::time::sleep(std::time::Duration::from_millis(120)).await; }
        }
        Ok((slot, out))
    }

    /// getMultipleAccounts of at most 100 keys, only bytes `[offset, offset + length)` of each (`dataSlice`): headers
    /// of large accounts (a programdata account's 45 bytes instead of megabytes); returns (slot, accounts in order)
    pub async fn accounts_slice(&self, keys: &[Pk], offset: usize, length: usize) -> Result<(u64, Vec<Option<Account>>)> {
        anyhow::ensure!(keys.len() <= 100, "accounts_slice takes at most 100 keys");
        let ks: Vec<String> = keys.iter().map(b58).collect();
        let r = self.call("getMultipleAccounts", json!([ks, { "encoding": "base64", "commitment": "processed", "dataSlice": { "offset": offset, "length": length } }])).await?;
        let slot = r["context"]["slot"].as_u64().unwrap_or(0);
        let out = r["value"].as_array().context("getMultipleAccounts: no value")?.iter().map(parse_account).collect();
        Ok((slot, out))
    }

    pub async fn slot(&self) -> Result<u64> { Ok(self.call("getSlot", json!([{ "commitment": "processed" }])).await?.as_u64().unwrap_or(0)) }

    pub async fn latest_blockhash(&self) -> Result<([u8; 32], u64)> {
        let r = self.call("getLatestBlockhash", json!([{ "commitment": "confirmed" }])).await?;
        let h = bs58::decode(r["value"]["blockhash"].as_str().context("no blockhash")?).into_vec()?;
        Ok((h.try_into().map_err(|_| anyhow::anyhow!("bad blockhash"))?, r["value"]["lastValidBlockHeight"].as_u64().unwrap_or(0)))
    }

    /// simulateTransaction (no signature check, replace blockhash); returns (err, units consumed, logs)
    pub async fn simulate(&self, tx: &[u8]) -> Result<(Option<Value>, Option<u64>, Vec<String>)> {
        let b64 = base64::engine::general_purpose::STANDARD.encode(tx);
        let r = self.call("simulateTransaction", json!([b64, { "encoding": "base64", "sigVerify": false, "replaceRecentBlockhash": true, "commitment": "processed" }])).await?;
        let v = &r["value"];
        let logs = v["logs"].as_array().map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect()).unwrap_or_default();
        Ok((if v["err"].is_null() { None } else { Some(v["err"].clone()) }, v["unitsConsumed"].as_u64(), logs))
    }

    /// simulateTransaction with everything the step-2 record needs: the slot simulated at, the error, units, logs
    pub async fn simulate_full(&self, tx: &[u8]) -> Result<Sim> {
        let b64 = base64::engine::general_purpose::STANDARD.encode(tx);
        let r = self.call("simulateTransaction", json!([b64, { "encoding": "base64", "sigVerify": false, "replaceRecentBlockhash": true, "commitment": "processed" }])).await?;
        let v = &r["value"];
        Ok(Sim { slot: r["context"]["slot"].as_u64().unwrap_or(0), err: if v["err"].is_null() { None } else { Some(v["err"].clone()) },
            units: v["unitsConsumed"].as_u64(),
            logs: v["logs"].as_array().map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect()).unwrap_or_default() })
    }

    /// getTransaction (confirmed, v0 allowed); None while the node doesn't have it
    pub async fn transaction(&self, sig: &str) -> Result<Option<Value>> {
        let r = self.call("getTransaction", json!([sig, { "encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed" }])).await?;
        Ok(if r.is_null() { None } else { Some(r) })
    }

    /// mints `owner` holds a token account for (SPL Token and Token-2022)
    pub async fn token_mints(&self, owner: &Pk) -> Result<std::collections::HashSet<Pk>> {
        let mut out = std::collections::HashSet::new();
        for prog in [*crate::pda::TOKEN_PROGRAM, *crate::pda::TOKEN_2022] {
            let r = self.call("getTokenAccountsByOwner", json!([b58(owner), { "programId": b58(&prog) }, { "encoding": "base64", "dataSlice": { "offset": 0, "length": 32 } }])).await?;
            for a in r["value"].as_array().into_iter().flatten() {
                if let Some(d) = a["account"]["data"][0].as_str().and_then(|d| base64::engine::general_purpose::STANDARD.decode(d).ok()) {
                    if let Ok(m) = Pk::try_from(d.as_slice()) { out.insert(m); }
                }
            }
        }
        Ok(out)
    }

    /// getSignatureStatuses: (slot, ok) per signature, None if unknown
    pub async fn statuses(&self, sigs: &[[u8; 64]]) -> Result<Vec<Option<(u64, bool)>>> {
        let ss: Vec<String> = sigs.iter().map(|s| bs58::encode(s).into_string()).collect();
        let r = self.call("getSignatureStatuses", json!([ss, { "searchTransactionHistory": false }])).await?;
        Ok(r["value"].as_array().map(|a| a.iter().map(|v| if v.is_null() { None } else {
            Some((v["slot"].as_u64().unwrap_or(0), v["err"].is_null())) }).collect()).unwrap_or_default())
    }
}

/// A reply's JSON: parsed in place when small, in `spawn_blocking` when over `runtime::LARGE_REPLY` bytes (a getBlock
/// or a big getMultipleAccounts: tens of ms of parsing that must not hold a runtime worker)
pub async fn parse_reply<B: AsRef<[u8]> + Send + 'static>(bytes: B) -> serde_json::Result<Value> {
    if bytes.as_ref().len() <= crate::runtime::LARGE_REPLY || tokio::runtime::Handle::try_current().is_err() { return serde_json::from_slice(bytes.as_ref()); }
    crate::runtime::BLOCKING_NOW.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    crate::runtime::LARGE_PARSES.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let r = tokio::task::spawn_blocking(move || { crate::runtime::check_not_hot("a large RPC reply's parse"); serde_json::from_slice(bytes.as_ref()) }).await;
    crate::runtime::BLOCKING_NOW.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
    match r { Ok(v) => v, Err(e) => Err(serde::de::Error::custom(format!("parse task: {e}"))) }
}

/// one simulateTransaction answer
#[derive(Debug, Clone)]
pub struct Sim { pub slot: u64, pub err: Option<Value>, pub units: Option<u64>, pub logs: Vec<String> }

fn parse_account(v: &Value) -> Option<Account> {
    if v.is_null() { return None; }
    let data = base64::engine::general_purpose::STANDARD.decode(v["data"][0].as_str()?).ok()?;
    let owner: Pk = bs58::decode(v["owner"].as_str()?).into_vec().ok()?.try_into().ok()?;
    Some(Account { owner, lamports: v["lamports"].as_u64().unwrap_or(0), data })
}
