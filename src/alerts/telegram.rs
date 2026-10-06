//! The Bot API call (`sendMessage`) and the redaction every text from it goes through.
//!
//! The token is in the request URL (`/bot<token>/sendMessage`), so an HTTP library error that names the URL would name
//! the token: every error is taken `without_url`, and every text that leaves this module (errors, API descriptions)
//! has the token, its secret half, anything shaped like a bot token, and every URL past its host removed ([`redact`]).
//! The API is reached over HTTPS only (I-10); a plain `http://` base is accepted for a loopback address (the tests'
//! fake server) and nothing else.
use std::time::Duration;

/// the Bot API (HTTPS only)
pub const API: &str = "https://api.telegram.org";

/// Why a `sendMessage` did not deliver, its text already redacted
#[derive(Debug, Clone, PartialEq)]
pub enum PostErr {
    /// HTTP 429: wait this long (the API's `retry_after`), then send again
    RetryAfter(Duration, String),
    /// a transport error, a timeout, a 5xx: send again after a backoff
    Transient(String),
    /// the API refused for good (a bad token, the bot not in the chat, a bad request): not sent again
    Permanent(String),
    /// the API could not parse the message's HTML: send it again as plain text
    Parse(String),
    /// the group became a supergroup: its new chat id (send again there; the operator updates the .env)
    Migrated(String, String),
}

impl PostErr {
    pub fn text(&self) -> &str {
        match self { PostErr::RetryAfter(_, s) | PostErr::Transient(s) | PostErr::Permanent(s) | PostErr::Parse(s) | PostErr::Migrated(_, s) => s }
    }
}

/// Whether `base` may carry the token: `https://`, or `http://` to a loopback address (tests)
pub fn base_ok(base: &str) -> bool {
    if base.starts_with("https://") { return true; }
    let Some(rest) = base.strip_prefix("http://") else { return false };
    let host = rest.split(['/', '?']).next().unwrap_or("");
    let host = host.rsplit_once(':').map_or(host, |(h, p)| if p.bytes().all(|b| b.is_ascii_digit()) { h } else { host });
    matches!(host, "127.0.0.1" | "localhost" | "[::1]")
}

/// The HTTP client of one sender: bounded connect and request times; HTTPS only unless the base is a loopback address
/// (the tests' fake server, reached without any environment proxy); no redirect followed (the API never redirects, and
/// a redirect must not take a request anywhere else)
pub fn client(timeout: Duration, https_only: bool) -> Result<reqwest::Client, String> {
    let b = reqwest::Client::builder().connect_timeout(timeout.min(Duration::from_secs(5))).timeout(timeout).https_only(https_only)
        .pool_idle_timeout(Duration::from_secs(60)).redirect(reqwest::redirect::Policy::none());
    let b = if https_only { b } else { b.no_proxy() };
    b.build().map_err(|e| format!("building the HTTP client: {}", chain(&e.without_url())))
}

/// an error and its sources, `: `-joined
fn chain(e: &(dyn std::error::Error + 'static)) -> String {
    let mut s = e.to_string();
    let mut src = e.source();
    while let Some(x) = src {
        let t = x.to_string();
        if !s.contains(&t) { s.push_str(": "); s.push_str(&t); }
        src = x.source();
    }
    s
}

/// `s` with the token, its secret half (after the colon) and their URL-encoded forms replaced, anything shaped like a
/// bot token (6-12 digits, a colon, 25 or more of `[A-Za-z0-9_-]`) masked, and every URL cut to its host (`rpc::scrub`)
pub fn redact(s: &str, token: &str) -> String {
    let mut o = s.to_string();
    let mut forms: Vec<String> = Vec::new();
    if token.len() >= 8 {
        forms.push(token.to_string());
        forms.push(token.replace(':', "%3A"));
        forms.push(token.replace(':', "%3a"));
        if let Some((_, secret)) = token.split_once(':') { if secret.len() >= 8 { forms.push(secret.to_string()); } }
    }
    for f in forms { if !f.is_empty() { o = o.replace(&f, "<redacted>"); } }
    crate::rpc::scrub(&mask_token_shapes(&o))
}

/// `s` with the token's forms replaced and token shapes masked, URLs kept (a message's text: its links must stay whole)
pub fn strip_token(s: &str, token: &str) -> String {
    let mut o = s.to_string();
    if token.len() >= 8 {
        let mut forms = vec![token.to_string(), token.replace(':', "%3A"), token.replace(':', "%3a")];
        if let Some((_, secret)) = token.split_once(':') { if secret.len() >= 8 { forms.push(secret.to_string()); } }
        for f in forms { o = o.replace(&f, "<redacted>"); }
    }
    mask_token_shapes(&o)
}

/// mask every `<6-12 digits>:<25+ of [A-Za-z0-9_-]>` (a bot token, whoever's) as `<redacted>`
pub fn mask_token_shapes(s: &str) -> String {
    let b = s.as_bytes();
    let tail_ok = |c: u8| c.is_ascii_alphanumeric() || c == b'_' || c == b'-';
    let mut out = String::with_capacity(s.len());
    let mut i = 0;
    let mut copied = 0;
    while i < b.len() {
        if b[i] == b':' {
            let mut d = i;
            while d > 0 && b[d - 1].is_ascii_digit() { d -= 1; }
            let digits = i - d;
            // the token's own URL form is `.../bot<token>/...`
            let before_ok = d == 0 || !b[d - 1].is_ascii_alphanumeric() || (d >= 3 && &b[d - 3..d] == b"bot");
            let mut e = i + 1;
            while e < b.len() && tail_ok(b[e]) { e += 1; }
            if (6..=12).contains(&digits) && before_ok && e - i - 1 >= 25 && d >= copied {
                out.push_str(&s[copied..d]);
                out.push_str("<redacted>");
                copied = e;
                i = e;
                continue;
            }
        }
        i += 1;
    }
    out.push_str(&s[copied..]);
    out
}

/// One `sendMessage` to `chat`: `text` as HTML (`html`) or plain. The message id on success
pub async fn post(c: &reqwest::Client, base: &str, token: &str, chat: &str, text: &str, html: bool) -> Result<i64, PostErr> {
    if !base_ok(base) { return Err(PostErr::Permanent("the alerts API base is not https (I-10): refused".into())); }
    let url = format!("{base}/bot{token}/sendMessage");
    let mut body = serde_json::json!({ "chat_id": chat, "text": text, "disable_web_page_preview": true });
    if html { body["parse_mode"] = serde_json::json!("HTML"); }
    let resp = match c.post(&url).json(&body).send().await {
        Ok(r) => r,
        Err(e) => {
            let what = if e.is_timeout() { "timed out" } else if e.is_connect() { "could not connect" } else { "request failed" };
            return Err(PostErr::Transient(redact(&format!("{what}: {}", chain(&e.without_url())), token)));
        }
    };
    let status = resp.status().as_u16();
    let bytes = match resp.bytes().await {
        Ok(b) => b,
        Err(e) => return Err(PostErr::Transient(redact(&format!("HTTP {status}: reading the reply: {}", chain(&e.without_url())), token))),
    };
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap_or(serde_json::Value::Null);
    if status == 200 && v["ok"] == serde_json::json!(true) { return Ok(v["result"]["message_id"].as_i64().unwrap_or(0)); }
    let desc_raw = v["description"].as_str().map(str::to_string).unwrap_or_else(|| String::from_utf8_lossy(&bytes[..bytes.len().min(400)]).into_owned());
    // redacted before it is cut: a cut through the token would leave a piece no form matches
    let desc = super::format::cut(&redact(&desc_raw, token), 300);
    let code = v["error_code"].as_u64().unwrap_or(status as u64);
    if status == 429 || code == 429 {
        let s = v["parameters"]["retry_after"].as_u64().unwrap_or(5).clamp(1, 3_600);
        return Err(PostErr::RetryAfter(Duration::from_secs(s), format!("HTTP 429 (retry after {s} s): {desc}")));
    }
    if let Some(m) = v["parameters"]["migrate_to_chat_id"].as_i64() {
        return Err(PostErr::Migrated(m.to_string(), format!("HTTP {status}: the group moved to a new chat id (update the .env): {desc}")));
    }
    if status == 400 && desc_raw.contains("can't parse entities") { return Err(PostErr::Parse(format!("HTTP 400: {desc}"))); }
    if status >= 500 || status == 200 { return Err(PostErr::Transient(format!("HTTP {status}: {desc}"))); }
    Err(PostErr::Permanent(format!("HTTP {status}: {desc}")))
}
