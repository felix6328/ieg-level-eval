# LevelEval 2.0 · IEG 游戏内容评测工作台

策划可在同一冻结题库上比较文字冒险关卡的生成配置，查看规则、语义和原文证据，确认问题样本，再用批准的 Golden Case 追踪改进。

## 本机启动

本机交付的 IEG Worktree 已准备 Python 环境。在 Worktree 根目录运行以下命令，打开 [LevelEval 2.0](http://127.0.0.1:8872/)。

```bash
scripts/run_ieg.sh
```

新 checkout 可以从 Python 3.11+ 安装。前端由同一个 FastAPI 进程提供静态 HTML、CSS 和 JavaScript。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
scripts/run_ieg.sh
```

默认端口 8872，SQLite 位于 `data/ieg/workspace.sqlite`。可用 `LEVEL_EVAL_PORT`、`LEVEL_EVAL_DB` 切换。WXG 原有 CLI、静态浏览和历史归档继续由稳定版本使用。

## 演示流程

1. 进入「实验中心」，选历史 24 题的冻结版本、A/B/C 三组、3 次重复、历史 Replay，创建实验。等队列完成后查看解析失败及重试记录。
2. 打开 A 组 `cyber_easy` 且重复号为 0 的输出。在评测工作台查看原始关卡、规则和 Terra 模型参照的原文引证。可在「Judge 校准」查看 Terra 40 条、任务独立留出与历史 Judge 稳定性。
3. 打开 B 组 `adv_hard_casual` 且重复号为 0 的输出。查看 Trace 或创建 Bad Case，以案件为入口生成 Golden 候选。也可输入修改理由并运行一次归档重写对照。
4. 在「Bad / Golden Case」验证候选断言，由策划登记审核人与理由后批准、发布。新冻结版本出现在「数据集」。
5. 对新版本启动匹配的 Replay，打开「回归与选型报告」生成配对回归。选全量实验生成选型报告，并下载 JSON。

## 数据和运行口径

- **历史归档**为 WXG 稳定版原始产物、用量与指标。**REPLAY** 使用已存输出，重新执行 IEG 校验；不产生新生成调用。旧运行参数缺证据时，显示重构请求和可追溯原文件。
- **Terra 模型参照**用于模型间分析和缩小人工复核范围。事实校验由程序核对字段与原文。仅有明确人工操作时才写审核结果，独立盲评与已看到模型的人工决定分开。
- **MOCK** 是流程演练。**REAL** 通过 OpenAI-compatible Provider 实际发送请求。使用环境变量 `LEVEL_EVAL_ENABLE_REAL=1`、`LEVEL_EVAL_API_KEY`（或 `SILICONFLOW_API_KEY`）及选填的 `LEVEL_EVAL_BASE_URL`。实验必须配置费用上限。自定义模型还需 `LEVEL_EVAL_PRICES_JSON`，值为模型 ID 到每百万输入和输出 token 的估算价格数组。
- 归档缺完整 HTTP 收据、远端种子和真人处理时长。费用报告统计使用估算口径，实际账单不可计算。历史 24 题适用于文字冒险单关卡，跨关卡路径、角色/物品状态和真实玩家行为需要更丰富的数据契约。
- 本机版本使用 macOS/Linux 的文件锁实现单工作进程。已有 Model/Prompt 组可直接比较，多个自定义配置可各建实验后同范围比较。

## 文档

- [项目审计](00_project_audit.md) · [数据血缘](01_data_lineage.md) · [产品差距](02_product_gap_analysis.md) · [实施计划及指标](03_implementation_plan.md)
- [实验与题库](04_experiments.md) · [评测与校准](05_evaluation.md) · [审核与分流](06_triage.md) · [案例与闭环](07_governance.md) · [选型与回归](08_reports.md)
- [验收报告](09_acceptance.md)
