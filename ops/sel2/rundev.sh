set -a; . /root/sniper/deploy/.env; set +a
cd /root/sel2
python3 -I dev_identity.py creators /root/sel/pos_mints.json /root/sel2/pos_creator.json
python3 -I dev_identity.py creators /root/sel/neg_mints.json /root/sel2/neg_creator.json
python3 -I dev_identity.py counts /root/sel2/pos_creator.json /root/sel2/neg_creator.json --out /root/sel2/creator_counts.json
echo DEVDONE
