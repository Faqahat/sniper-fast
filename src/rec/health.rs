//! Health streams (PLAN WP-02 item 10; MEASUREMENT §4.9 feedhealth.jsonl, §4.10 resources.jsonl) and the recorder's
//! monitor thread.
//!
//! - **resources.jsonl**, every 10 s from the monitor thread: process CPU, the engine thread's CPU, RSS, threads, load,
//!   recorder queues and bytes, disk, UDP receive drops of our sockets (`/proc/net/udp`), per-runtime busy time.
//! - **feedhealth.jsonl**, every 10 s, one line per feed (the state stream as `state`): built here from the feed
//!   counters, written by the engine's housekeeping, which holds the per-feed first-arrival counts and lead times
//!   (txarr: a signature's arrivals are final when it leaves the 10 s window, so those two lag by 10 s).
//! - The monitor also runs the disk budget every 10 s ([`super::disk`]) and writes manifest.json every 60 s.
use super::{disk, manifest, Queue, Record, Recorder, RESOURCES};
use crate::feeds::{clock::now_ns, FeedCounters};
use crate::lat::Series;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering::Relaxed};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub const EVERY: Duration = Duration::from_secs(10);
pub const MANIFEST_EVERY: Duration = Duration::from_secs(60);

pub(super) fn monitor(r: Arc<Recorder>, stop: Arc<AtomicBool>) {
    crate::runtime::nice_this_thread(crate::runtime::BG_NICE);
    let mut fs = disk::RealFs;
    let mut res = Resources::new(r.started_ns);
    let _ = manifest::write(&r, false);
    let (mut next, mut next_manifest, mut next_writers) = (Instant::now() + EVERY, Instant::now() + MANIFEST_EVERY, Instant::now() + Duration::from_secs(1));
    let mut seen = [(0u64, Instant::now(), false); 5];
    while !stop.load(Relaxed) {
        std::thread::sleep(Duration::from_millis(50));
        let now = Instant::now();
        // the writer threads, every second: one that ended, or a core / slow one stuck with records queued (review F2)
        if now >= next_writers { next_writers = now + Duration::from_secs(1); r.check_writers(&mut seen); }
        if now >= next {
            next = now + EVERY;
            r.disk_check(&mut fs);
            let line = res.line(&r);
            r.push(RESOURCES, None, 0, Record::Json(line));
        }
        if now >= next_manifest { next_manifest = now + MANIFEST_EVERY; let _ = manifest::write(&r, false); }
    }
}

// ------------------------------------------------------------------ resources.jsonl

/// resources.jsonl lines, with the previous values their deltas need
pub struct Resources { seq: u64, last_t: u64, prev_cpu: Option<(u64, u64)>, prev_engine: Option<u64>, prev_bytes: HashMap<String, u64>,
    prev_busy: Option<(u64, u64)>, prev_udp: Option<u64> }

impl Resources {
    pub fn new(t0: u64) -> Resources { Resources { seq: 0, last_t: t0, prev_cpu: None, prev_engine: None, prev_bytes: HashMap::new(), prev_busy: None, prev_udp: None } }

    pub fn line(&mut self, r: &Recorder) -> Value {
        let t = now_ns();
        let stat = proc_stat("/proc/self/stat");
        let cpu = stat.as_ref().map(|s| (s.utime_ms, s.stime_ms));
        let d = |now: Option<u64>, prev: Option<u64>| now.zip(prev).map(|(a, b)| a.saturating_sub(b));
        let tid = r.engine_tid.load(Relaxed);
        let engine = (tid > 0).then(|| proc_stat(&format!("/proc/self/task/{tid}/stat"))).flatten().map(|s| s.utime_ms + s.stime_ms);
        let mut queues = serde_json::Map::new();
        for q in Queue::ALL {
            let (now, hwm) = r.take_queue_hwm_iv(q);
            let qs = &r.queues[q as usize];
            queues.insert(q.as_str().into(), json!({ "now": now, "hwm_delta": hwm, "bytes_now": qs.bytes.load(Relaxed), "bytes_hwm": qs.bytes_hwm.load(Relaxed) }));
        }
        let mut bytes = serde_json::Map::new();
        for s in &r.streams {
            let b = s.written_bytes.load(Relaxed);
            let prev = self.prev_bytes.insert(s.spec.name.clone(), b).unwrap_or(0);
            if b > prev { bytes.insert(s.spec.name.clone(), json!(b - prev)); }
        }
        let (used, free) = { let l = r.disk.lock().unwrap_or_else(|e| e.into_inner()); (l.used_bytes, l.fs_free_bytes) };
        let runtimes = r.runtimes.get().map(|(hot, bg)| {
            let busy = (crate::runtime::busy_ms(hot), crate::runtime::busy_ms(bg));
            let prev = self.prev_busy.replace(busy);
            json!({ "hot": { "busy_ms_delta": prev.map(|p| busy.0.saturating_sub(p.0)), "tasks_now": crate::runtime::tasks_now(hot),
                    // RPC work polled on an arbx-hot thread (review N5; 0 unless a client was not bound to rt_bg)
                    "rpc_violations_total": crate::runtime::hot_violations() },
                "bg": { "busy_ms_delta": prev.map(|p| busy.1.saturating_sub(p.1)), "tasks_now": crate::runtime::tasks_now(bg),
                    "blocking_now": crate::runtime::BLOCKING_NOW.load(Relaxed) } })
        });
        // the kernel's receive drops of our UDP sockets; the raw feeds' counters get their own port's
        let udp = udp_drops_by_port();
        for (port, c) in r.udp.lock().unwrap_or_else(|e| e.into_inner()).iter() { if let Some(n) = udp.get(port) { c.store(*n, Relaxed); } }
        let udp_total: Option<u64> = (!udp.is_empty()).then(|| udp.values().sum());
        let line = json!({ "seq": self.seq, "t_ns": t, "interval_ns": t.saturating_sub(self.last_t),
            "cpu_user_ms_delta": d(cpu.map(|c| c.0), self.prev_cpu.map(|c| c.0)), "cpu_sys_ms_delta": d(cpu.map(|c| c.1), self.prev_cpu.map(|c| c.1)),
            "engine_cpu_ms_delta": d(engine, self.prev_engine),
            "rss_bytes_now": rss_bytes(), "threads_now": stat.as_ref().map(|s| s.threads), "load_avg_1m_now": load_avg(),
            "recorder_queues": queues, "recorder_bytes_delta": bytes,
            "disk": { "run_dir_bytes_now": used, "fs_free_bytes_now": free },
            "udp_drops_delta": d(udp_total, self.prev_udp),
            // the per-(role, provider) RPC registry is WP-03b's (F29)
            "rpc": null,
            "runtimes": runtimes });
        self.seq += 1;
        self.last_t = t;
        if cpu.is_some() { self.prev_cpu = cpu; }
        if engine.is_some() { self.prev_engine = engine; }
        if udp_total.is_some() { self.prev_udp = udp_total; }
        line
    }
}

pub struct ProcStat { pub utime_ms: u64, pub stime_ms: u64, pub threads: u64 }

/// `/proc/<pid>[/task/<tid>]/stat`: CPU times (ms) and threads
pub fn proc_stat(path: &str) -> Option<ProcStat> {
    let text = std::fs::read_to_string(path).ok()?;
    parse_stat(&text)
}

pub fn parse_stat(text: &str) -> Option<ProcStat> {
    // the command name is in parentheses and may hold spaces: fields count from the last ')'
    let rest = &text[text.rfind(')')? + 1..];
    let f: Vec<&str> = rest.split_whitespace().collect();
    // f[0] is field 3 (state): utime is field 14, stime 15, num_threads 20
    let tck = clk_tck();
    let ms = |i: usize| -> Option<u64> { Some(f.get(i)?.parse::<u64>().ok()? * 1000 / tck) };
    Some(ProcStat { utime_ms: ms(11)?, stime_ms: ms(12)?, threads: f.get(17)?.parse().ok()? })
}

fn clk_tck() -> u64 {
    // SAFETY: a plain sysconf query
    let t = unsafe { libc::sysconf(libc::_SC_CLK_TCK) };
    if t > 0 { t as u64 } else { 100 }
}

fn rss_bytes() -> Option<u64> {
    let text = std::fs::read_to_string("/proc/self/statm").ok()?;
    let pages: u64 = text.split_whitespace().nth(1)?.parse().ok()?;
    // SAFETY: a plain sysconf query
    let page = unsafe { libc::sysconf(libc::_SC_PAGESIZE) }.max(4096) as u64;
    Some(pages * page)
}

fn load_avg() -> Option<f64> { std::fs::read_to_string("/proc/loadavg").ok()?.split_whitespace().next()?.parse().ok() }

/// The kernel's receive-drop count of each UDP socket of this process, by local port (`/proc/net/udp`, `udp6`)
pub fn udp_drops_by_port() -> HashMap<u16, u64> {
    let mine: std::collections::HashSet<u64> = std::fs::read_dir("/proc/self/fd").into_iter().flatten().flatten().filter_map(|e| {
        let l = std::fs::read_link(e.path()).ok()?;
        l.to_str()?.strip_prefix("socket:[")?.strip_suffix(']')?.parse().ok()
    }).collect();
    let mut out = HashMap::new();
    if mine.is_empty() { return out; }
    for f in ["/proc/net/udp", "/proc/net/udp6"] {
        let Ok(text) = std::fs::read_to_string(f) else { continue };
        for (port, inode, drops) in parse_proc_udp(&text) {
            if mine.contains(&inode) { *out.entry(port).or_insert(0) += drops; }
        }
    }
    out
}

/// (local port, inode, drops) of each line of a `/proc/net/udp` table
pub fn parse_proc_udp(text: &str) -> Vec<(u16, u64, u64)> {
    text.lines().skip(1).filter_map(|l| {
        let c: Vec<&str> = l.split_whitespace().collect();
        let port = u16::from_str_radix(c.get(1)?.rsplit(':').next()?, 16).ok()?;
        Some((port, c.get(9)?.parse().ok()?, c.get(12)?.parse().ok()?))
    }).collect()
}

// ------------------------------------------------------------------ feedhealth.jsonl

#[derive(Default, Clone)]
struct FeedPrev { packets: u64, txs: u64, forwarded: u64, first: u64, chan: u64, udp: Option<u64>, shreds: [u64; 6] }

/// feedhealth.jsonl lines (§4.9), with what their deltas need
#[derive(Default)]
pub struct FeedHealth { seq: u64, last_t: u64, prev: Vec<FeedPrev> }

/// one feed for [`FeedHealth::lines`]: its id (None: the state stream), counters and lead-time series
pub struct FeedRow<'a> { pub id: Option<u16>, pub c: &'a FeedCounters, pub lead: Option<&'a mut Series> }

impl FeedHealth {
    pub fn new(t0: u64) -> FeedHealth { FeedHealth { seq: 0, last_t: t0, prev: Vec::new() } }

    /// One line per feed. `tip`: the newest processed slot (for `slot_lag_now`)
    pub fn lines(&mut self, t: u64, tip: u64, rows: Vec<FeedRow>) -> Vec<Value> {
        if self.prev.len() < rows.len() { self.prev.resize(rows.len(), FeedPrev::default()); }
        let interval = t.saturating_sub(self.last_t);
        let mut out = Vec::with_capacity(rows.len());
        for (i, row) in rows.into_iter().enumerate() {
            let c = row.c;
            let p = &mut self.prev[i];
            let ld = |a: &std::sync::atomic::AtomicU64| a.load(Relaxed);
            let (packets, txs, fwd, first, chan) = (ld(&c.packets), ld(&c.txs), ld(&c.forwarded), ld(&c.first_arrivals), ld(&c.channel_drops));
            let last = ld(&c.last_msg_ns);
            let slot = ld(&c.slot_max);
            let udp = c.udp_watched.load(Relaxed).then(|| ld(&c.udp_drops));
            let sh = &c.shreds;
            let shv = [ld(&sh.data), ld(&sh.code), ld(&sh.dup), ld(&sh.bad), ld(&sh.sets_ok), ld(&sh.sets_failed)];
            let shreds = sh.on.load(Relaxed).then(|| json!({ "data_delta": shv[0] - p.shreds[0].min(shv[0]), "code_delta": shv[1] - p.shreds[1].min(shv[1]),
                "dup_delta": shv[2] - p.shreds[2].min(shv[2]), "bad_delta": shv[3] - p.shreds[3].min(shv[3]), "sets_ok_delta": shv[4] - p.shreds[4].min(shv[4]),
                "sets_failed_delta": shv[5] - p.shreds[5].min(shv[5]), "version": sh.version.load(Relaxed) }));
            out.push(json!({ "seq": self.seq, "t_ns": t, "interval_ns": interval,
                "feed": row.id, "name": c.name, "kind": c.kind, "connected_now": c.connected.load(Relaxed),
                "reconnects_total": ld(&c.reconnects), "errors_total": ld(&c.errors),
                "packets_delta": packets.saturating_sub(p.packets), "txs_delta": txs.saturating_sub(p.txs), "forwarded_delta": fwd.saturating_sub(p.forwarded),
                "first_arrivals_delta": first.saturating_sub(p.first),
                "lead_ms": row.lead.map(|s| s.take_interval(1e6)),
                "last_msg_age_ms_now": (last > 0).then(|| t.saturating_sub(last) as f64 / 1e6),
                "slot_max_now": (slot > 0).then_some(slot), "slot_lag_now": (slot > 0 && tip > 0).then(|| tip as i64 - slot as i64),
                // the provider's created_at is not parsed yet (WP-03)
                "provider_lag_ms": null,
                "shreds": shreds,
                "udp_drops_delta": udp.map(|u| u.saturating_sub(p.udp.unwrap_or(0))),
                "channel_drops_delta": chan.saturating_sub(p.chan) }));
            *p = FeedPrev { packets, txs, forwarded: fwd, first, chan, udp, shreds: shv };
            self.seq += 1;
        }
        self.last_t = t;
        out
    }
}
