#!/usr/bin/env bash
# 一键复跑（第二轮完整流程）。模型调用按请求内容哈希缓存在 logs/cache/（不入库）；
# 有缓存时 0 花费；无缓存时整套约 ¥6–7（见 COST.md），超过 configs/settings.yaml 的 budget_cny 自动熔断。
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=$PWD
python scripts/run_generate.py            # 216 关：3 组 × 24 spec × 3 次采样
python scripts/run_judge.py               # 第一轮：规则层 + 评审 v0/v1（72 关 s0）
python scripts/run_judge_v1_new.py        # v0/v1 补评留出集 2 的 15 关
python scripts/run_judge_v3.py all        # v3 清单 × 三家族（216 关）
python scripts/run_judge_v3.py retest     # 40 个标注关卡换 seed 重评（重测信度）
python scripts/compute_agreement.py       # 评审 vs 参照：dev / holdout / 合格判定 → eval/agreement.md
python scripts/run_pairwise_eval.py 30    # 成对比较 vs 绝对打分 → eval/pairwise_eval.md
python scripts/analyze_v3.py              # 合格率 + 聚类 bootstrap + ICC + 敏感性 → eval/results_v3.md
python scripts/run_rewrite_loop.py B,C    # 定向重写闭环
python scripts/report_rewrite.py          # → eval/rewrite_loop.md
python scripts/report_retest.py           # → eval/retest.md
python scripts/analyze.py > /dev/null     # 第一轮对照表 → eval/results.md
python scripts/build_html.py              # 标注页 + 浏览器
echo "完成：见 eval/results_v3.md、eval/agreement.md、eval/rewrite_loop.md、viewer/index.html"
