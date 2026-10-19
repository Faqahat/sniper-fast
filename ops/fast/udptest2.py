import socket, time, os
# after a 20 ms idle: send #1, spin `gap` us, send #2: is #2 cheap (queue still hot)?  TEST-NET-1 (dropped upstream)
os.sched_setaffinity(0, {2})
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('192.0.2.1', 9)); b = b'\x00' * 1100
pc = time.perf_counter_ns
for gap in (0, 5, 10, 20, 40, 80, 160):
    a1, a2 = [], []
    for i in range(60):
        time.sleep(0.02)
        t = pc(); s.send(b); t1 = pc()
        while pc() - t1 < gap * 1000: pass
        t2 = pc(); s.send(b); t3 = pc()
        a1.append(t1 - t); a2.append(t3 - t2)
    a1.sort(); a2.sort()
    print(f'gap {gap:4d}us: first p50 {a1[30]/1e3:6.1f} p90 {a1[54]/1e3:6.1f} | second p50 {a2[30]/1e3:6.1f} p90 {a2[54]/1e3:6.1f}')
