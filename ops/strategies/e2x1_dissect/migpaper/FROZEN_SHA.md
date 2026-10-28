# migpaper frozen artefacts (10-28 23:33 PKT) — never refit during the run

| file (data/migpaper/models/) | sha256 | what |
|---|---|---|
| p30.json | e2a35cf32d3399c19db7d7d18805731368c7b96781b8254ad532a47038b0818c | p30 predictor, 21664 rows, 400 iterations |
| p120.json | 0abd92e9088ca38d4174b634c7000daa00993974e47c17dac1632c4033caea40 | p120 predictor, 21664 rows, 400 iterations |
| cont.json | db313fdc6eaddd46c97938e1713380fe0a2e7c02ef2e348d1c587e712c105cb5 | continuation model (pd stop), 79442 checkpoints, 200 iterations |
| dly.json | f6b7c0f5489ab470ba36d23ad0798c8445ec437b615188a2ca7cf499cd12c553 | landing delays (slots): 0.1099, 0.1534, 0.1947, 0.2376, 0.2837, 0.3478, 0.4205, 0.5340, 0.6756, 1.0229 |
| ../wstore.npz | ee9a4edc7b6e65d00be8f3dbb427ea38dd70101bca7f7d8bba60dfa08597c2bb | initial wallet store, 2878349 trips (migrate wallets.npz, through 10-28 21:26 PKT) |
| ../cstore.npz | f921e95861878f59a9f8d1afd8b31daa543dae8d346866153c85c39829ed9ace | initial creator store, 237970 creates |

Fit log:
```
VAL p30: n_iter 400 AUC test 0.8681 | max|p - feat_p.pkl| = 0.00e+00 | numpy export max diff 1.11e-16
VAL p120: n_iter 400 AUC test 0.7855 | max|p - feat_p.pkl| = 0.00e+00 | numpy export max diff 2.22e-16
FROZEN p30: fit rows 21664 n_iter 400 in-sample AUC 0.9624 | numpy export max diff 1.11e-16 | sha256 e2a35cf32d3399c19db7d7d18805731368c7b96781b8254ad532a47038b0818c
   OOF p30 AUC over frozen rows 0.8853
FROZEN p120: fit rows 21664 n_iter 400 in-sample AUC 0.9331 | numpy export max diff 2.22e-16 | sha256 0abd92e9088ca38d4174b634c7000daa00993974e47c17dac1632c4033caea40
   OOF p120 AUC over frozen rows 0.8088
VAL cont: 43042 checkpoints (train rows) n_iter 200 | numpy export max diff 2.22e-16
FROZEN cont: 79442 checkpoints n_iter 200 | numpy export max diff 2.22e-16 | sha256 db313fdc6eaddd46c97938e1713380fe0a2e7c02ef2e348d1c587e712c105cb5
wstore: 2878349 trips, 804615 wallets, t_end max 10-28 21:27 PKT, 59 MB
wstore check vs m1 crossing-wallet features on 300 rows: max abs diff 0.0002
cstore: 237970 creates; check vs m1 creator features on 300 rows: max abs diff 0
features check (mplib.features vs feat.pkl on 7 V=105 first-crossing rows of the grad tape): max abs diff 3.815e-06
```
