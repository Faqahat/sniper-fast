//! Message formatting for Telegram's HTML mode (`parse_mode` HTML). Every piece of outside data that goes into a
//! message (mint names, routes, error and panic texts, segment and stream names) is escaped here, and titles and bodies
//! are built only from escaped pieces: a mint called `<b>` or an error holding `&` cannot break a message or inject
//! markup. Messages stay under Telegram's 4,096-character limit by whole alerts (an alert too long on its own is sent
//! as escaped plain text, cut).
use super::Alert;

/// a message's HTML source at most (Telegram: 4,096 characters after entity parsing)
pub const MAX_TEXT: usize = 3_800;
/// a field's text at most (errors, details) before it is escaped
pub const MAX_FIELD: usize = 300;

/// HTML-escape text for Telegram (`&`, `<`, `>` and `"`, for attribute values)
pub fn esc(s: &str) -> String {
    let mut o = String::with_capacity(s.len() + 8);
    for c in s.chars() {
        match c {
            '&' => o.push_str("&amp;"),
            '<' => o.push_str("&lt;"),
            '>' => o.push_str("&gt;"),
            '"' => o.push_str("&quot;"),
            _ => o.push(c),
        }
    }
    o
}

/// At most `max` characters of `s` on a character boundary ("…" marks a cut), control characters other than a new
/// line or a tab removed
pub fn cut(s: &str, max: usize) -> String {
    let clean = s.chars().filter(|c| !c.is_control() || *c == '\n' || *c == '\t');
    let mut o = String::new();
    let mut n = 0;
    for c in clean {
        if n + 1 > max.max(1) {
            o.pop();
            o.push('…');
            return o;
        }
        o.push(c);
        n += 1;
    }
    o
}

/// text, cut to `max` characters, then escaped
pub fn text(s: &str, max: usize) -> String { esc(&cut(s, max)) }

/// `n` with thousands separators: 12,345
pub fn int(n: u64) -> String {
    let s = n.to_string();
    let mut o = String::with_capacity(s.len() + s.len() / 3);
    for (i, c) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 { o.push(','); }
        o.push(c);
    }
    o
}

/// lamports as SOL with 4 to 9 decimals ("0.0340", "0.000005", "1.25"), a leading "-" when negative
pub fn sol(l: i64) -> String {
    let a = l.unsigned_abs();
    let mut frac = format!("{:09}", a % 1_000_000_000);
    while frac.len() > 4 && frac.ends_with('0') { frac.pop(); }
    format!("{}{}.{frac} SOL", if l < 0 { "-" } else { "" }, a / 1_000_000_000)
}

/// signed SOL: "+0.0012 SOL", "-0.000005 SOL"
pub fn sol_signed(l: i64) -> String { if l >= 0 { format!("+{}", sol(l)) } else { sol(l) } }

/// lamports as SOL without the unit (a breakdown's parts: `tip 0.0001 · fee 0.000005`)
pub fn sol_num(l: i64) -> String { sol(l).trim_end_matches(" SOL").to_string() }

/// signed, without the unit: "+0.0012"
pub fn sol_num_signed(l: i64) -> String { if l >= 0 { format!("+{}", sol_num(l)) } else { sol_num(l) } }

/// a base58 key or signature as `abcd…wxyz` (the whole of a short one)
pub fn short_key(s: &str) -> String {
    let c: Vec<char> = s.chars().collect();
    if c.len() <= 12 { return s.to_string(); }
    format!("{}…{}", c[..4].iter().collect::<String>(), c[c.len() - 4..].iter().collect::<String>())
}

/// whether `s` is a base58 transaction signature (87-88 characters of the alphabet; 64 to 90 accepted)
pub fn is_signature(s: &str) -> bool {
    (64..=90).contains(&s.len()) && s.bytes().all(|b| b.is_ascii_alphanumeric() && !matches!(b, b'0' | b'O' | b'I' | b'l'))
}

/// the solscan link of a transaction, None unless `sig` is a base58 signature (nothing else goes into an href)
pub fn solscan_tx(sig: &str) -> Option<String> {
    is_signature(sig).then(|| format!("<a href=\"https://solscan.io/tx/{sig}\">solscan</a>"))
}

/// a duration in seconds for people: 45s, 12m, 2h13m, 3d4h
pub fn dur(s: u64) -> String {
    match s {
        0..=99 => format!("{s}s"),
        100..=3_599 => format!("{}m", s / 60),
        3_600..=172_799 => format!("{}h{:02}m", s / 3_600, s % 3_600 / 60),
        _ => format!("{}d{}h", s / 86_400, s % 86_400 / 3_600),
    }
}

/// the civil date (year, month, day) of a day number since 1970-01-01
pub fn civil(days: i64) -> (i64, u32, u32) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let month = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (yoe + era * 400 + if month <= 2 { 1 } else { 0 }, month, day)
}

/// `YYYY-MM-DD` (UTC) of a time in ns
pub fn utc_date(t_ns: u64) -> String {
    let (y, m, d) = civil((t_ns / 1_000_000_000 / 86_400) as i64);
    format!("{y:04}-{m:02}-{d:02}")
}

/// `HH:MM:SS` (UTC) of a time in ns
pub fn utc_hms(t_ns: u64) -> String {
    let s = t_ns / 1_000_000_000 % 86_400;
    format!("{:02}:{:02}:{:02}", s / 3_600, s % 3_600 / 60, s % 60)
}

/// The body of an alert: lines of parts joined by " · ". Every value is escaped and cut here; `raw` takes HTML made
/// by this module (links)
#[derive(Default, Clone, Debug)]
pub struct Body { lines: Vec<Vec<String>> }

impl Body {
    pub fn new() -> Body { Body { lines: vec![Vec::new()] } }
    fn part(mut self, p: String) -> Body {
        if self.lines.is_empty() { self.lines.push(Vec::new()); }
        if let Some(l) = self.lines.last_mut() { l.push(p); }
        self
    }
    /// `key value` (value escaped)
    pub fn kv(self, k: &str, v: impl AsRef<str>) -> Body { let p = format!("{} {}", esc(k), text(v.as_ref(), MAX_FIELD)); self.part(p) }
    /// `key <code>value</code>` (value escaped)
    pub fn code(self, k: &str, v: impl AsRef<str>) -> Body {
        let p = if k.is_empty() { format!("<code>{}</code>", text(v.as_ref(), MAX_FIELD)) } else { format!("{} <code>{}</code>", esc(k), text(v.as_ref(), MAX_FIELD)) };
        self.part(p)
    }
    /// plain text (escaped)
    pub fn txt(self, s: impl AsRef<str>) -> Body { let p = text(s.as_ref(), MAX_FIELD); self.part(p) }
    /// HTML this module made (a link)
    pub fn raw(self, html: String) -> Body { self.part(html) }
    /// the next parts go on a new line
    pub fn nl(mut self) -> Body { if self.lines.last().is_some_and(|l| !l.is_empty()) { self.lines.push(Vec::new()); } self }
    pub fn html(&self) -> String {
        self.lines.iter().filter(|l| !l.is_empty()).map(|l| l.join(" · ")).collect::<Vec<_>>().join("\n")
    }
}

/// One alert as HTML: `<icon> <b>title</b> (+n like it …)` and its body; an alert older than a minute at `now_ns` (it
/// waited for the rate, a retry, or its dedup window) says when it happened
pub fn render(a: &Alert, now_ns: u64) -> String {
    let mut s = format!("{} <b>{}</b>", a.icon, a.title);
    if a.repeats > 0 { s.push_str(&format!(" <i>(+{} like it since the last)</i>", int(a.repeats))); }
    if now_ns.saturating_sub(a.t_ns) > 60_000_000_000 { s.push_str(&format!(" <i>(at {} UTC)</i>", utc_hms(a.t_ns))); }
    if !a.body.is_empty() { s.push('\n'); s.push_str(&a.body); }
    s
}

/// `html` without its tags and with its entities decoded: the text Telegram would show (the plain-text fallback)
pub fn to_plain(html: &str) -> String {
    let mut o = String::with_capacity(html.len());
    let mut in_tag = false;
    for c in html.chars() {
        match c {
            '<' => in_tag = true,
            '>' if in_tag => in_tag = false,
            _ if !in_tag => o.push(c),
            _ => {}
        }
    }
    o.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&amp;", "&")
}

/// `html` made to fit `max` characters: as is when it does, else its text, cut and escaped (no markup left to break)
pub fn fit(html: &str, max: usize) -> String {
    if html.chars().count() <= max { return html.to_string(); }
    let plain = to_plain(html);
    let mut k = max;
    loop {
        let e = esc(&cut(&plain, k));
        if e.chars().count() <= max || k <= 8 { return e; }
        k = k * 3 / 4;
    }
}

/// One message from the alerts at the front of `alerts`: a header line (`arbx · <label> · HH:MM:SS UTC`), then as many
/// whole alerts as fit in `max` characters (at least one). Returns the text and how many alerts it holds
pub fn compose(label: &str, t_ns: u64, alerts: &[Alert], max: usize) -> (String, usize) {
    let head = format!("<b>arbx</b> · {} · {} UTC", text(label, 80), utc_hms(t_ns));
    let mut out = head.clone();
    let mut len = out.chars().count();
    let mut n = 0;
    for a in alerts {
        let room = max.saturating_sub(head.chars().count() + 2);
        let r = fit(&render(a, t_ns), room);
        let rl = r.chars().count() + 2;
        if n > 0 && len + rl > max { break; }
        out.push_str("\n\n");
        out.push_str(&r);
        len += rl;
        n += 1;
    }
    (out, n)
}
