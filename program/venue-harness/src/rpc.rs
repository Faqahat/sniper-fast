//! Minimal read-only JSON-RPC client for the fixture fetcher: public mainnet RPC through the system `curl`, at most
//! 2.5 requests per second (one every 400 ms, under the 3 req/s budget), with backoff on errors and 429s. Only
//! `getAccountInfo` and `getMultipleAccounts` are used; nothing is ever sent.
use base64::Engine as _;
use serde_json::{json, Value};
use solana_account::Account;
use solana_address::Address;
use std::io::Write;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

pub const MAINNET: &str = "https://api.mainnet-beta.solana.com";

pub struct Rpc { pub url: String, pub min_interval: Duration, last: Option<Instant>, pub requests: usize }

impl Rpc {
    pub fn new(url: &str) -> Self { Rpc { url: url.into(), min_interval: Duration::from_millis(400), last: None, requests: 0 } }

    fn pace(&mut self) {
        if let Some(t) = self.last {
            let e = t.elapsed();
            if e < self.min_interval { std::thread::sleep(self.min_interval - e); }
        }
        self.last = Some(Instant::now());
    }

    pub fn call(&mut self, method: &str, params: Value) -> Result<Value, String> {
        let body = json!({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).to_string();
        let mut last_err = String::new();
        for attempt in 0..6 {
            self.pace();
            self.requests += 1;
            let mut child = Command::new("curl")
                .args(["-sS", "--max-time", "120", "-X", "POST", "-H", "Content-Type: application/json", "--data-binary", "@-",
                       "-w", "\n%{http_code}", &self.url])
                .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
                .spawn().map_err(|e| format!("curl: {e}"))?;
            child.stdin.take().unwrap().write_all(body.as_bytes()).map_err(|e| e.to_string())?;
            let out = child.wait_with_output().map_err(|e| e.to_string())?;
            let text = String::from_utf8_lossy(&out.stdout);
            let (payload, code) = text.rsplit_once('\n').unwrap_or((&text, ""));
            if out.status.success() && code == "200" {
                let v: Value = serde_json::from_str(payload).map_err(|e| format!("{method}: bad json: {e}"))?;
                if let Some(err) = v.get("error") { return Err(format!("{method}: {err}")); }
                return Ok(v["result"].clone());
            }
            last_err = format!("{method}: http {code} {} {}", String::from_utf8_lossy(&out.stderr).trim(), &payload[..payload.len().min(200)]);
            std::thread::sleep(Duration::from_secs(2 + 2 * attempt));
        }
        Err(last_err)
    }

    /// (context slot, account or None) per key; at most 100 keys (one request, one slot)
    pub fn multiple_accounts(&mut self, keys: &[Address]) -> Result<(u64, Vec<Option<Account>>), String> {
        assert!(keys.len() <= 100, "getMultipleAccounts takes at most 100 keys");
        let ks: Vec<String> = keys.iter().map(|k| k.to_string()).collect();
        let r = self.call("getMultipleAccounts", json!([ks, {"encoding": "base64", "commitment": "confirmed"}]))?;
        let slot = r["context"]["slot"].as_u64().ok_or("no context slot")?;
        let vals = r["value"].as_array().ok_or("no value")?;
        if vals.len() != keys.len() { return Err(format!("getMultipleAccounts: {} values for {} keys", vals.len(), keys.len())); }
        Ok((slot, vals.iter().map(decode_account).collect::<Result<Vec<_>, _>>()?))
    }

    pub fn account(&mut self, key: &Address) -> Result<(u64, Option<Account>), String> {
        let r = self.call("getAccountInfo", json!([key.to_string(), {"encoding": "base64", "commitment": "confirmed"}]))?;
        let slot = r["context"]["slot"].as_u64().ok_or("no context slot")?;
        Ok((slot, decode_account(&r["value"])?))
    }
}

fn decode_account(v: &Value) -> Result<Option<Account>, String> {
    if v.is_null() { return Ok(None); }
    let data = v["data"][0].as_str().ok_or("account without base64 data")?;
    let data = base64::engine::general_purpose::STANDARD.decode(data).map_err(|e| e.to_string())?;
    let owner = v["owner"].as_str().ok_or("no owner")?.parse::<Address>().map_err(|e| e.to_string())?;
    // rentEpoch is u64::MAX for rent-exempt accounts; JSON may carry it as a float
    let rent_epoch = v["rentEpoch"].as_u64().unwrap_or(u64::MAX);
    Ok(Some(Account { lamports: v["lamports"].as_u64().ok_or("no lamports")?, data, owner, executable: v["executable"].as_bool().unwrap_or(false), rent_epoch }))
}

pub fn now_utc() -> String {
    // RFC 3339 without a date crate: civil-from-days (H. Hinnant)
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs() as i64;
    let (days, rem) = (secs.div_euclid(86_400), secs.rem_euclid(86_400));
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + if m <= 2 { 1 } else { 0 };
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z", rem / 3600, rem % 3600 / 60, rem % 60)
}
