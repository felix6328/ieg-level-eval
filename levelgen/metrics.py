"""一致性指标：Spearman、二次加权 Kappa、Cohen's Kappa、MAE、精确/±1 一致率。不依赖 sklearn。"""
import math, random
import numpy as np
from scipy.stats import spearmanr

def to_int(x):   # 评审中位数可能是 .5：按「打不准取低分」向下取整
    return int(math.floor(x)) if x is not None else None

def kappa(a, b, k=5, weights=None):
    a = [int(x) - 1 for x in a]; b = [int(x) - 1 for x in b]
    O = np.zeros((k, k))
    for i, j in zip(a, b): O[i, j] += 1
    n = O.sum()
    E = np.outer(O.sum(1), O.sum(0)) / n
    if weights == "quadratic": W = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    elif weights == "linear": W = np.array([[abs(i - j) for j in range(k)] for i in range(k)]) / (k - 1)
    else: W = 1 - np.eye(k)
    den = (W * E).sum()
    return float("nan") if den == 0 else 1 - (W * O).sum() / den

def agreement(pred, ref):
    """pred 可为小数（用于 Spearman/MAE），kappa 用向下取整后的整数。"""
    pairs = [(p, r) for p, r in zip(pred, ref) if p is not None and r is not None]
    if len(pairs) < 3: return None
    p, r = zip(*pairs)
    pi = [to_int(x) for x in p]
    rho = spearmanr(p, r).statistic
    return {"n": len(pairs), "spearman": float(rho) if rho == rho else float("nan"),
            "qwk": kappa(pi, r, weights="quadratic"), "cohen_kappa": kappa(pi, r),
            "mae": float(np.mean([abs(a - b) for a, b in zip(p, r)])),
            "exact": float(np.mean([a == b for a, b in zip(pi, r)])),
            "within1": float(np.mean([abs(a - b) <= 1 for a, b in zip(p, r)]))}

def bootstrap_spearman(pred, ref, n=2000, seed=0):
    rnd = random.Random(seed); idx = list(range(len(pred))); out = []
    for _ in range(n):
        s = [rnd.choice(idx) for _ in idx]
        a = [pred[i] for i in s]; b = [ref[i] for i in s]
        if len(set(a)) > 1 and len(set(b)) > 1: out.append(spearmanr(a, b).statistic)
    out.sort(); return (out[int(.025 * len(out))], out[int(.975 * len(out))]) if out else (None, None)
