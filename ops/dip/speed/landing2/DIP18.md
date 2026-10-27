# dip18: Falcon native UDP lane (built 10-25 ~23:50 PKT; owner "yes" to the Falcon UDP lane)

- Engine: /root/sniper-dip/snipe_engine_dip18 (sha256 34ed37f2…) = dip17 + `kind = "falcon-udp"`.
  - Datagram = the 16-byte raw key UUID + the raw tx (≤ 1,232 bytes); UDP 9000; no reply.
  - Tip ≥ 0.001 SOL to a Fa1con1… account, else the copy is refused; 5 TPS per key.
- Tests: 57 engine + 709 library tests pass. Txs are byte-identical when no falcon-udp path is named (golden test).
- Side file per server: /root/sniper-dip/paths_falcon_udp.toml (local copies in sniper-data/speed_fixes/paths_falcon_udp_{fra,ams}.toml).
  - Path name "falcon-udp"; url udp://fra.falcon.wtf:9000 or udp://ams.falcon.wtf:9000.
- run_dip_prod.sh md5 b305d2ec: naming falcon-udp in --routes or --probe-paths appends the side file and picks dip18.
  - New preset --routes v11 = v10 + falcon-udp next to falcon HTTP on BAM / Jito / Harmonic leaders.
  - Falcon UDP and HTTP use the same key and tip group, so each copy carries one tip.
- Unknowns: UDP drops are silent (if nothing lands, replay the signed tx to http://fra.falcon.wtf to read the reason); whether duplicate datagrams count against the 5 TPS (1 datagram per copy by default).

## FRA run 21 (the owner starts it after stopping run 20; AMS pre-send must have ended)
```bash
sudo bash /root/prod/run_dip_prod.sh --run 21 --trades 60 --size 0.35 --tier wider --tp off --sl 0.5 --hold-slots 5 --dev-list /root/sniper-dip/dev_list.txt --dev-size 0.35 --near /root/sniper-dip/near_leaders_fra.txt --nonce /root/prod/nonce_fra.txt --fallback ck --m2 /root/dip/m2_v3_reg4_top25.json --m2-mode gate --presend --presend-whale-pct 6 --presend-live --presend-live-size-sol 0.35 --presend-live-k 4 --presend-live-routes "default=helius-ps" --presend-live-max-per-sec 20 --presend-live-path-max-per-sec 20 --presend-live-max-fills 100 --presend-live-fee-budget-sol 0.1 --sell-fanout helius-swqos --routes v11 --skip-clients Rakurai --loaded-data-limit 16777216 --route-headers --window-clock --clock2 --minutes 240
```
