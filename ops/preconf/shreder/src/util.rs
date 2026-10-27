//! Small helpers: clocks, PKT time formatting, access (endpoint/token) file, redaction, process stats.

use std::path::Path;

/// CLOCK_REALTIME in ns (the same clock the engines use for their `t` fields).
#[inline]
pub fn now_ns() -> i64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(libc::CLOCK_REALTIME, &mut ts) };
    ts.tv_sec as i64 * 1_000_000_000 + ts.tv_nsec as i64
}

pub const PKT_OFFSET_S: i64 = 5 * 3600;

/// days since 1970-01-01 -> (y, m, d)   (H. Hinnant's civil_from_days)
pub fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

/// PKT wall-clock parts of a CLOCK_REALTIME ns value: (y, mo, d, h, mi, s)
pub fn pkt_parts(ns: i64) -> (i64, u32, u32, u32, u32, u32) {
    let s = ns.div_euclid(1_000_000_000) + PKT_OFFSET_S;
    let days = s.div_euclid(86400);
    let sod = s.rem_euclid(86400) as u32;
    let (y, mo, d) = civil_from_days(days);
    (y, mo, d, sod / 3600, (sod / 60) % 60, sod % 60)
}

pub fn fmt_hms_pkt(ns: i64) -> String {
    let (_, _, _, h, mi, s) = pkt_parts(ns);
    format!("{h:02}:{mi:02}:{s:02}")
}

/// file key "YYYYMMDD_HH" (PKT hour)
pub fn hour_key(ns: i64) -> String {
    let (y, mo, d, h, _, _) = pkt_parts(ns);
    format!("{y:04}{mo:02}{d:02}_{h:02}")
}

/// hour bucket number (for cheap rotation checks)
#[inline]
pub fn hour_bucket(ns: i64) -> i64 {
    (ns.div_euclid(1_000_000_000) + PKT_OFFSET_S).div_euclid(3600)
}

/// seconds until the next PKT wall time HH:MM (today or tomorrow)
pub fn secs_until_pkt(hhmm: &str, now: i64) -> Result<f64, String> {
    let (h, m) = hhmm.split_once(':').ok_or("--until wants HH:MM")?;
    let h: i64 = h.trim().parse().map_err(|_| "bad hour")?;
    let m: i64 = m.trim().parse().map_err(|_| "bad minute")?;
    if !(0..24).contains(&h) || !(0..60).contains(&m) {
        return Err("--until out of range".into());
    }
    let now_s = now as f64 / 1e9 + PKT_OFFSET_S as f64;
    let sod = now_s.rem_euclid(86400.0);
    let mut d = (h * 3600 + m * 60) as f64 - sod;
    if d <= 0.0 {
        d += 86400.0;
    }
    Ok(d)
}

pub const DEFAULT_ENDPOINT: &str = "http://fra-allnodes.binary.shreder.xyz:9991";

/// Where the endpoint / token came from. Values are NEVER printed; use `fingerprint()` in logs.
#[derive(Clone)]
pub struct Access {
    pub endpoint: String,
    pub token: Option<String>,
    pub header: String,
    pub source: String,
}

impl Access {
    /// short non-reversible id so logs can show WHICH endpoint was used without revealing it
    pub fn fingerprint(&self) -> String {
        format!("{:08x}", fnv1a(self.endpoint.as_bytes()))
    }
    pub fn auth_desc(&self) -> String {
        match &self.token {
            Some(t) => format!("token in '{}' header ({} chars)", self.header, t.len()),
            None => "none (IP allowlist)".into(),
        }
    }
    pub fn secrets(&self) -> Vec<String> {
        let mut v = vec![self.endpoint.clone()];
        if let Some(h) = host_of(&self.endpoint) {
            v.push(h);
        }
        if let Some(t) = &self.token {
            if t.len() >= 4 {
                v.push(t.clone());
            }
        }
        v
    }
}

pub fn fnv1a(b: &[u8]) -> u32 {
    let mut h: u32 = 0x811c9dc5;
    for &x in b {
        h ^= x as u32;
        h = h.wrapping_mul(0x01000193);
    }
    h
}

pub fn host_of(url: &str) -> Option<String> {
    let rest = url.split_once("://").map(|(_, r)| r).unwrap_or(url);
    let hostport = rest.split('/').next()?;
    let host = hostport.rsplit_once(':').map(|(h, _)| h).unwrap_or(hostport);
    if host.is_empty() {
        None
    } else {
        Some(host.to_string())
    }
}

fn normalize_endpoint(s: &str) -> String {
    let s = s.trim();
    if s.starts_with("http://") || s.starts_with("https://") {
        s.to_string()
    } else {
        format!("http://{s}")
    }
}

/// Access file format (all optional; missing file = defaults = IP-allowlist on the default endpoint):
///   endpoint = http://host:port      (or a bare line that starts with http:// / https://, or host:port)
///   token = XXXX                     (or any other bare line)
///   header = x-token                 (metadata key for the token; e.g. `authorization` with token `Bearer XXX`)
///   # comments and blank lines ignored
/// Precedence: --endpoint flag > file > built-in default.
pub fn load_access(path: Option<&Path>, endpoint_flag: Option<&str>) -> Result<Access, String> {
    let mut endpoint: Option<String> = None;
    let mut token: Option<String> = None;
    let mut header = "x-token".to_string();
    let mut source = "default".to_string();
    if let Some(p) = path {
        if p.exists() {
            let txt = std::fs::read_to_string(p).map_err(|e| format!("cannot read access file: {}", e.kind()))?;
            source = "file".into();
            for raw in txt.lines() {
                let line = raw.trim();
                if line.is_empty() || line.starts_with('#') {
                    continue;
                }
                if let Some((k, v)) = line.split_once('=') {
                    let k = k.trim().to_ascii_lowercase();
                    let v = v.trim().trim_matches('"').to_string();
                    match k.as_str() {
                        "endpoint" | "url" | "grpc" => endpoint = Some(normalize_endpoint(&v)),
                        "token" | "x-token" | "key" | "auth" => {
                            if !v.is_empty() {
                                token = Some(v)
                            }
                        }
                        "header" | "token_header" => header = v.to_ascii_lowercase(),
                        _ => {}
                    }
                    continue;
                }
                let looks_url = line.starts_with("http://")
                    || line.starts_with("https://")
                    || (line.contains(':') && line.contains('.') && !line.contains(' '));
                if looks_url && endpoint.is_none() {
                    endpoint = Some(normalize_endpoint(line));
                } else if token.is_none() {
                    token = Some(line.to_string());
                }
            }
        }
    }
    if let Some(e) = endpoint_flag {
        endpoint = Some(normalize_endpoint(e));
        source = format!("{source}+flag");
    }
    let endpoint = endpoint.unwrap_or_else(|| DEFAULT_ENDPOINT.to_string());
    Ok(Access { endpoint, token, header, source })
}

/// replace every secret occurrence in `msg`
pub fn redact(msg: &str, secrets: &[String]) -> String {
    let mut m = msg.to_string();
    for s in secrets {
        if !s.is_empty() {
            m = m.replace(s.as_str(), "<redacted>");
        }
    }
    // never let a newline split a log line
    m.replace('\n', " ").replace('"', "'")
}

/// (user+sys CPU seconds, max RSS KB)
pub fn rusage() -> (f64, i64) {
    let mut ru: libc::rusage = unsafe { std::mem::zeroed() };
    unsafe { libc::getrusage(libc::RUSAGE_SELF, &mut ru) };
    let cpu = ru.ru_utime.tv_sec as f64 + ru.ru_utime.tv_usec as f64 / 1e6 + ru.ru_stime.tv_sec as f64 + ru.ru_stime.tv_usec as f64 / 1e6;
    (cpu, ru.ru_maxrss as i64)
}

/// current RSS in MB from /proc/self/statm
pub fn rss_mb() -> f64 {
    std::fs::read_to_string("/proc/self/statm")
        .ok()
        .and_then(|s| s.split_whitespace().nth(1).and_then(|x| x.parse::<f64>().ok()))
        .map(|pages| pages * 4096.0 / 1e6)
        .unwrap_or(0.0)
}

/// filesystem use% like df (used / (used + avail)) for the fs holding `p`
pub fn disk_used_pct(p: &Path) -> Option<f64> {
    use std::ffi::CString;
    use std::os::unix::ffi::OsStrExt;
    let c = CString::new(p.as_os_str().as_bytes()).ok()?;
    let mut st: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::statvfs(c.as_ptr(), &mut st) } != 0 {
        return None;
    }
    let used = (st.f_blocks - st.f_bfree) as f64;
    let avail = st.f_bavail as f64;
    if used + avail <= 0.0 {
        return None;
    }
    Some(100.0 * used / (used + avail))
}

pub fn pctl(sorted: &[i64], p: f64) -> i64 {
    if sorted.is_empty() {
        return 0;
    }
    let i = ((sorted.len() - 1) as f64 * p).round() as usize;
    sorted[i.min(sorted.len() - 1)]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pkt_format() {
        // 2026-10-27 19:30:00 UTC = 2026-10-28 00:30:00 PKT
        let ns = 1_793_129_400i64 * 1_000_000_000;
        assert_eq!(fmt_hms_pkt(ns), "00:30:00");
        assert_eq!(hour_key(ns), "20261028_00");
    }

    #[test]
    fn access_file_forms() {
        let d = std::env::temp_dir().join(format!("shreder_rec_test_{}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        let f = d.join("k1");
        std::fs::write(&f, "# c\nendpoint = fra.example.xyz:9991\ntoken = abcd1234\n").unwrap();
        let a = load_access(Some(&f), None).unwrap();
        assert_eq!(a.endpoint, "http://fra.example.xyz:9991");
        assert_eq!(a.token.as_deref(), Some("abcd1234"));
        std::fs::write(&f, "https://x.example.com:443\nSECRETTOKEN\n").unwrap();
        let a = load_access(Some(&f), None).unwrap();
        assert_eq!(a.endpoint, "https://x.example.com:443");
        assert_eq!(a.token.as_deref(), Some("SECRETTOKEN"));
        let r = redact("err connecting to x.example.com with SECRETTOKEN", &a.secrets());
        assert!(!r.contains("x.example.com") && !r.contains("SECRETTOKEN"), "{r}");
        let a = load_access(Some(&d.join("missing")), None).unwrap();
        assert_eq!(a.endpoint, DEFAULT_ENDPOINT);
        assert!(a.token.is_none());
        let a = load_access(None, Some("10.0.0.1:9991")).unwrap();
        assert_eq!(a.endpoint, "http://10.0.0.1:9991");
        std::fs::remove_dir_all(&d).ok();
    }

    #[test]
    fn until_math() {
        let ns = 1_793_129_400i64 * 1_000_000_000; // 00:30:00 PKT
        assert!((secs_until_pkt("01:45", ns).unwrap() - 4500.0).abs() < 1e-6);
        assert!((secs_until_pkt("00:29", ns).unwrap() - (86400.0 - 60.0)).abs() < 1e-6);
    }
}
