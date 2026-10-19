import socket, time, os
# idle gap as SPIN (vCPU never halts) vs SLEEP; TEST-NET-1 (dropped upstream)
os.sched_setaffinity(0, {2})
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('192.0.2.1', 9)); b = b'\x00' * 1100
pc = time.perf_counter_ns
for mode in ('sleep', 'spin'):
    for gap_ms in (2, 20):
        a = []
        for i in range(60):
            if mode == 'sleep': time.sleep(gap_ms / 1e3)
            else:
                t0 = pc()
                while pc() - t0 < gap_ms * 1e6: pass
            t = pc(); s.send(b); a.append(pc() - t)
        a.sort(); print(f'{mode} {gap_ms:2d} ms gap: first send p50 {a[30]/1e3:6.1f} p90 {a[54]/1e3:6.1f} us')
