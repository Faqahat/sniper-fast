#!/bin/bash
until grep -q PAPER_SMOKE_DONE /root/gap/final/paper_pall.log; do sleep 5; done
curl -s -m 10 https://api.mainnet-beta.solana.com -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getBalance\",\"params\":[\"FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS\"]}" > /root/gap/final/wallet_fin2_before.json
/root/gap/final/dry_final.sh fin2 15
curl -s -m 10 https://api.mainnet-beta.solana.com -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getBalance\",\"params\":[\"FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS\"]}" > /root/gap/final/wallet_fin2_after.json
