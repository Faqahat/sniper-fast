"""The owner's Stage 0 win-mix rule (docs/field-tests/FT-008-auto-pool-refresh.md, "Stage 0 exit"): each win counts by
the token its route trades through (attempts.jsonl `route.mint`). Common tokens are the stablecoins, the liquid-staking
SOL tokens, the wrapped majors and the listed protocol tokens; every other token is a meme (pump.fun, bonk.fun and other
launches).

The table is by mint (a token's identity), never by symbol: each mint below was checked against DexScreener's token API
(symbol and name) on 2026-10-07. A meme can carry a common token's symbol; `LOOKALIKES` names the ones seen in our wins,
so a report can say why its count differs from one made by symbol."""
from __future__ import annotations

COMMON = {
    # stablecoins
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB": "USD1",
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo": "PYUSD",
    # liquid-staking SOL
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "JupSOL",
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1": "bSOL",
    "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm": "INF",
    # wrapped majors
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "WBTC",
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "cbBTC",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "WETH",
    "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS": "ZEC",
    # protocol tokens
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "METvsvVRapdj9cFLzq4Tr43xK4tAjQfwX76z3n6mWQL": "MET",
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
    "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE": "ORCA",
    "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL": "JTO",
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": "PYTH",
    "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ": "W",
    "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7": "DRIFT",
    "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS": "KMNO",
    "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4": "JLP",
    "BLVxek8YMXUQhcKmMvrFTrzh5FXg8ec88Crp6otEaCMf": "BELIEVE",
    "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn": "PUMP",
    "4qQeZ5LwSz6HuupUu8jCtgXyW1mYQcNbFAW1sWZp89HL": "CAKE",
}

# memes whose symbol is a common token's (by mint they are memes)
LOOKALIKES = {
    "DAemPFNc3RtibBDKkUA4eL2Ns11q9VRdbpptmqm8DGqN": "symbol CAKE, name cake.xmr: not PancakeSwap's CAKE (4qQeZ5Lw...)",
}


def classify(mint: str | None) -> str:
    """`common` or `meme` by the route's mint (any mint not listed is a meme, the rule's "every other token");
    `unknown` when the record has no mint (WP-11 review #12: never counted as a meme)"""
    if not mint:
        return "unknown"
    return "common" if mint in COMMON else "meme"


def symbol(mint: str | None) -> str | None:
    return COMMON.get(mint)
