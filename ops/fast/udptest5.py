import socket, time, os
# after 20 ms idle: send on socket A (TEST-NET-1 192.0.2.1), spin 50 us, then send on socket B (TEST-NET-2 198.51.100.1) / same socket A
os.sched_setaffinity(0, {2})
A = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); A.connect(('192.0.2.1', 9))
B = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); B.connect(('198.51.100.1', 9))
b = b'\x00' * 1100; pc = time.perf_counter_ns
for label, second in (('same socket', A), ('other socket', B), ('other socket, 1-byte kick first', B)):
    a1, a2 = [], []
    for i in range(80):
        time.sleep(0.02)
        t = pc(); A.send(b if 'kick' not in label else b'\x00'); t1 = pc()
        while pc() - t1 < 50_000: pass
        t2 = pc(); second.send(b); t3 = pc()
        a1.append(t1 - t); a2.append(t3 - t2)
    a1.sort(); a2.sort()
    print(f'{label:34}: first p50 {a1[40]/1e3:6.1f} | second p50 {a2[40]/1e3:6.1f} p90 {a2[72]/1e3:6.1f}')
# cold TCP-like path proxy: second send from ANOTHER thread's earlier kick? (cross-CPU): kick from cpu 0, send from cpu 2
import threading
a2 = []
for i in range(80):
    time.sleep(0.02)
    th = threading.Thread(target=lambda: (os.sched_setaffinity(0, {0}), A.send(b'\x00'))); th.start(); th.join()
    t1 = pc()
    while pc() - t1 < 50_000: pass
    t2 = pc(); B.send(b); a2.append(pc() - t2)
a2.sort(); print(f'kick from another CPU, send here      : second p50 {a2[40]/1e3:6.1f} p90 {a2[72]/1e3:6.1f}')
