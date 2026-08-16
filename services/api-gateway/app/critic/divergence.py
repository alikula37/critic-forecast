import numpy as np


def divergence_matrix(p50_curves, price_scale):
    n = len(p50_curves)
    if n == 0:
        return [], 0.0
    mat = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = float(np.mean(np.abs(p50_curves[i] - p50_curves[j])) / max(price_scale, 1e-12))
            mat[i, j] = mat[j, i] = d
    divs = [float(np.mean(mat[i, mat[i] > 0])) if (mat[i] > 0).any() else 0.0 for i in range(n)]
    mean_div = float(np.mean(mat[mat > 0])) if (mat > 0).any() else 0.0
    return divs, mean_div


def consensus_from_divergence(mean_div, scale=0.1):
    return float(np.clip(1.0 - mean_div / scale, 0.0, 1.0))
