# Operating environments (owner, 2026-10-20)

| | DEV | PROD |
|---|---|---|
| Wallet | FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS | 2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE |
| Keystore on the server | /root/.nexus-v2-trading-wallet.enc | /root/prod/wallet-prod.enc (copy of the host's `~/arbed/wallets/trading-v3.enc`, the old arb bot's keystore) |
| Passphrase | /root/.nexus-v2-trading-wallet.pass (scripts run unattended) | typed by the owner at the engine's hidden prompt; never stored |
| Who starts it | Claude (only zero-cost dry runs / tests without the owner's explicit go) | the owner, manually, inside tmux |
| Scripts | /root/run1/run1.sh (live), dry_run1.sh (zero cost), cu_check.sh | /root/prod/run_prod.sh, unlock_test.sh, unwrap_prod.sh |
| Caps | fixed in run1_common.sh | explicit args: --size --max-buys --max-loss --minutes (+ --lock, --tag); hard limits in run_prod.sh |
| Logs | /root/run1/ | /root/prod/runs/ |

Both use the SAME engine build (/root/sniper-run1/target/release/snipe_engine), rule #2, gates, fees, exit and slot
deadline (run1_common.sh); PROD only swaps the wallet + caps. One engine per server at a time (both scripts refuse
otherwise). PROD refuses to start outside tmux, without a terminal, below the needed balance, or without typing PROD.

PROD start:
    ssh -p 1996 it@84.32.100.36
    tmux new -s prod            # or: tmux attach -t prod
    sudo bash /root/prod/run_prod.sh --size 1.5 --max-buys 20 --max-loss 0.5 --minutes 180 --tag p1
    (type PROD, then the keystore passphrase)   detach: Ctrl-b d   clean stop: Ctrl-c
First time: sudo bash /root/prod/unlock_test.sh  -> must print "payer = 2g7rYv7y...".

WSOL: pump v3 buys/sells settle in NATIVE SOL. The prod wallet held 4.23 WSOL (+0.07 native) on 2026-10-20: run
    sudo bash /root/prod/unwrap_prod.sh   (owner; passphrase; closes the WSOL account into native SOL)
before the first PROD run. run_prod.sh warns when WSOL > 0.01 is idle.
