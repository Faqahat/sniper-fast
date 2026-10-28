import pickle
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen"
Z = pickle.load(open(f"{W}/hab.pkl", "rb"))
H = {}
for p in Z["P"]:
    if p["D"] < 2: continue
    f = {k: v for k, v in p["f"].items() if k != "last"}
    H[(p["w"], p["mint"])] = (p["s"], f)
pickle.dump(H, open(f"{W}/hab_slim.pkl", "wb")); print(len(H))
