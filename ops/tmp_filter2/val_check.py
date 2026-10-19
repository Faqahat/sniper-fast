import json
h5=json.load(open("/root/last500/his_500.json"))
tape=json.load(open("/root/mirror/his_tape.json"))
hm={r["mint"]:r for r in h5}; tm={r["mint"]:r for r in tape}
toks={"PASS1":"6uQrPwv1DoX7x7QXMbiy1e9FR5mRyhMfqyS1rDFjpump",
      "PASS2":"EYo9mCUK72tqTGS7TGyzCBjG6zVrXLS2GbUaY8EfqHGF",
      "REJECT":"HNwcHVQeV9MqbR9KhEWZK62Mfv48awKh4RCtxmMbpump"}
for lbl,m in toks.items():
    print(lbl,m[:10],"in_h500=",m in hm,"in_tape=",m in tm)
    if m in hm:
        r=hm[m]
        print("   n03=%s nsl0=%s cosnip=%s dev=%s van=%s cfee=%s hr=%s img=%s peak=%s"%(
            r.get("n_trades_0_3"),r.get("n_trades_slot0"),r.get("cosnipers_slot0"),
            r.get("dev_buy"),r.get("vanilla"),r.get("creator_fee_bps"),r.get("holder_reward"),r.get("has_image"),r.get("peak_r")))
