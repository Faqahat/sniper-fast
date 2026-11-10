"""CV record of the exact config to freeze (gbm_s, a_spend dropped), on dev_chain_full.pkl."""
import sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatperfect")
import x8_variants as V, ftab
P,cols,X=ftab.table("/home/it/sniper-data/flatperfect/dev_chain_full.pkl")
V.P,V.cols,V.X=P,cols,X; V.ci={c:i for i,c in enumerate(cols)}
F=[c for c in cols if not c.startswith("L_") and c not in V.DROP and c!="a_spend"]
V.show("FINAL gbm_s -a_spend", V.cv(F, ("T2","rearm"), model="gbm_s"))
