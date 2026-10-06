//! manifest.json (MEASUREMENT §4.4): every stream's files, bytes, records, first and last time, drops, I/O and encoding
//! losses, queue high-water marks and, for closed files, their sha256; the queues; the disk budget's state; the
//! recorder's faults; the sampled populations' counts (`sampling`, WP-08). Written every 60 s by the monitor and at
//! close, atomically (temporary file + rename).
//!
//! `records_total` counts records whose bytes reached the disk. A record that was taken but not written is in exactly
//! one of `io_lost_total` (an open, compression or write error), `encode_errors_total` (its encoder panicked) or, at the
//! queue level, `queues.<q>.lost_at_close` (still queued when the writers stopped); `dropped_total`, `suppressed_total`
//! and `late_total` were never taken.
use super::{Class, Queue, Recorder};
use crate::feeds::clock::now_ns;
use serde_json::{json, Value};
use std::sync::atomic::Ordering::Relaxed;

pub const SCHEMA: &str = "arbx.manifest/1.0";

pub fn json(r: &Recorder, last: bool) -> Value {
    let streams: Vec<Value> = r.streams.iter().map(|s| {
        let files = s.files.lock().unwrap_or_else(|e| e.into_inner()).clone();
        let q = &r.queues[s.spec.queue as usize];
        json!({ "name": s.spec.name, "schema": s.spec.schema, "class": s.spec.class.as_str(), "files": files,
            "records_total": s.written_records.load(Relaxed), "dropped_total": s.dropped.load(Relaxed), "suppressed_total": s.suppressed.load(Relaxed),
            "late_total": s.late.load(Relaxed), "io_errors_total": s.io_errors.load(Relaxed), "io_lost_total": s.io_lost.load(Relaxed),
            "encode_errors_total": s.enc_errors.load(Relaxed), "on": s.on.load(Relaxed), "queue": s.spec.queue.as_str(),
            "queue_cap": if q.cap == u64::MAX { Value::Null } else { json!(q.cap) }, "queue_hwm": r.queue_hwm(s.spec.queue) })
    }).collect();
    let queues: serde_json::Map<String, Value> = Queue::ALL.iter().map(|&q| {
        let qs = &r.queues[q as usize];
        let cap = |c: u64| if c == u64::MAX { Value::Null } else { json!(c) };
        (q.as_str().to_string(), json!({ "cap": cap(qs.cap), "bytes_cap": cap(qs.byte_cap), "hwm": r.queue_hwm(q), "bytes_hwm": qs.bytes_hwm.load(Relaxed),
            "lost_at_close": qs.lost_at_close.load(Relaxed) }))
    }).collect();
    let disk = r.disk.lock().unwrap_or_else(|e| e.into_inner()).json();
    json!({ "schema": SCHEMA, "t_ns": now_ns(), "final": last, "run": r.run, "producer": r.producer, "started_ns": r.started_ns,
        "streams": streams, "queues": queues, "disk": disk, "core_record_loss": r.core_lost.load(Relaxed),
        "writers_dead": Class::ALL.iter().filter(|c| r.dead[c.idx()].load(Relaxed)).map(|c| c.as_str()).collect::<Vec<_>>(),
        "close_timeout": r.close_timeout.lock().unwrap_or_else(|e| e.into_inner()).clone(),
        "fatal": r.fatal.get(), "echo_dropped": r.echo_dropped.load(Relaxed),
        // plan addendum I-9 (WP-08): the sampled populations' totals (kept + left out = seen)
        "sampling": { "rivals_venues": r.rival_venues.counts(), "exec_unwatched": r.exec_unwatched.counts() } })
}

pub fn write(r: &Recorder, last: bool) -> anyhow::Result<()> {
    let v = json(r, last);
    crate::control::write_atomic(&r.dir.join("manifest.json"), serde_json::to_string_pretty(&v)?.as_bytes())
}
