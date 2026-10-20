set -a; . /root/sniper/deploy/.env; set +a
cd /root/sel2
for i in 1 2 3; do python3 -I meta_extract.py pos /root/sel/pos_mints.json /root/sel2/pos_meta.json /root/sel2/pos_recovered_clean.json /root/expanded_raw.json /root/sel/pos_feat.json; done
for i in 1 2; do python3 -I meta_extract.py neg /root/sel/neg_mints.json /root/sel2/neg_meta.json /root/sel/neg_feat.json; done
echo ALLDONE
