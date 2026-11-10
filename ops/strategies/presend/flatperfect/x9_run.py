import sys; sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatperfect")
import warnings; warnings.filterwarnings("ignore")
import x8_variants as V
for model in sys.argv[1].split(","):
    V.show(model+" all sep", V.cv(V.ALLF, ("T2","rearm"), model=model))
