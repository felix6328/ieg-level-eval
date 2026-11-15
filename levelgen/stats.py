"""统计工具：按 spec 聚类的 bootstrap（同一 spec 的 3 个样本一起抽）、配对差、组内相关 ICC(1)。"""
import random, statistics

def cluster_boot(by_spec, fn, B=4000, seed=0):
    """by_spec: {spec_id: [值...]}；fn: 把抽到的 [[值...],...] 变成一个统计量。返回 (点估计, 下界, 上界)。"""
    keys = sorted(by_spec); rng = random.Random(seed)
    pt = fn([by_spec[k] for k in keys]); bs = []
    for _ in range(B):
        bs.append(fn([by_spec[k] for k in rng.choices(keys, k=len(keys))]))
    bs.sort(); return pt, bs[int(.025 * B)], bs[int(.975 * B)]

def flat_mean(groups): return statistics.mean(x for g in groups for x in g)

def icc1(groups):
    """单因素随机效应 ICC(1)：spec 之间的方差占总方差的比例。越接近 1，说明分数主要由 spec 决定、同一 spec 多次生成很稳定。"""
    groups = [g for g in groups if len(g) > 1]
    k = statistics.mean(len(g) for g in groups); n = len(groups)
    grand = statistics.mean(x for g in groups for x in g)
    msb = sum(len(g) * (statistics.mean(g) - grand) ** 2 for g in groups) / (n - 1)
    msw = sum((x - statistics.mean(g)) ** 2 for g in groups for x in g) / sum(len(g) - 1 for g in groups)
    return (msb - msw) / (msb + (k - 1) * msw) if (msb + (k - 1) * msw) > 0 else float("nan")
