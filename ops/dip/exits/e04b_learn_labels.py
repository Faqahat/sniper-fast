#!/usr/bin/env python3
# labels of e04b (importable without e04b's command line): y[i, k-1] = mean over h in H of V(k + h) - V(k), k = 1..K-1
import numpy as np


def labels(d, H):
    K = d.K; Vv = d.tv[:, 0, :]
    N = len(d.t_did); y = np.zeros((N, K - 1))
    for k in range(1, K):
        acc = 0.0
        for h in H: acc = acc + Vv[:, min(K, k + h)] - Vv[:, k]
        y[:, k - 1] = acc / len(H)
    return y
