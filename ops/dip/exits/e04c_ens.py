#!/usr/bin/env python3
# e04c: the 3-seed ensemble of the e04b h1248 models (mean prediction, theta +0.0005 SOL, cap 20) -> e04b_ENS3_model.pkl + ksell
import sys, os, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e_apply as AP
D_ = E.DATA
pickle.dump(dict(ensemble=[f"{D_}/e04b_h1248_model.pkl", f"{D_}/e04b_h1248s2_model.pkl", f"{D_}/e04b_h1248s3_model.pkl"], theta=0.0005, cap=20),
            open(f"{D_}/e04b_ENS3_model.pkl", "wb"))
d = V.Data()
ks, _ = AP.apply_saved(d, f"{D_}/e04b_ENS3_model.pkl")
np.save(f"{D_}/e04b_ENS3_ksell.npy", ks); print("ENS3 saved, mean sell tick", ks.mean())
