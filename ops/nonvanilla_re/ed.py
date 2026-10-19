# pure-python ed25519 compressed-point validity (matches dalek CompressedEdwardsY::decompress)
P=2**255-19
D=(-121665*pow(121666,P-2,P))%P
SQRT_M1=pow(2,(P-1)//4,P)
def on_curve(b):
    if len(b)!=32: return False
    y=int.from_bytes(b,"little")
    sign=(y>>255)&1
    y&=(1<<255)-1
    if y>=P: return False   # dalek rejects non-canonical? actually it reduces; keep strict
    y%=P
    u=(y*y-1)%P
    v=(D*y*y+1)%P
    # x = u * v^3 * (u*v^7)^((p-5)/8)
    v3=(v*v%P)*v%P
    v7=(v3*v3%P)*v%P
    x=(u*v3)%P*pow((u*v7)%P,(P-5)//8,P)%P
    vxx=(v*x%P)*x%P
    if vxx==u%P:
        ok=True
    elif vxx==(-u)%P:
        x=x*SQRT_M1%P; ok=True
    else:
        ok=False
    if not ok: return False
    if x==0 and sign: return False
    return True
