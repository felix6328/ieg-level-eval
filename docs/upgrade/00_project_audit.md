# Phase 0 · LevelEval 项目审计

审计日期为 2026-11-20。审计对象是文字冒险关卡评测仓库 `ieg-level-eval`，基准提交为 `7ab99c766b1f203ccc30033f81280dffad2b6183`。原仓库 README 面向 IEG 介绍项目，WXG 简历的《AI 生成关卡的自动质检与模型选型》使用同一组评测数字，早期《LevelEval finish》任务也指明了此仓库。根据仓库和实验数据的匹配，将当前稳定提交记录为 `wxg-v1.0`。

## Git 与审计输入

- 原工作区为 `main`，本地 `origin/main` 指向同一提交。工作区干净，审计开始时无本地 Tag 或其他工作树。克隆深度为 1，提交记录只覆盖本地可见的稳定提交。
- 阅读了 `README.md`、`docs/DESIGN.md`、`docs/COST.md`、`docs/面试讲法.md`、WXG 简历项目说明和早期《LevelEval finish》验收说明。基准仓库内未找到 `docs/upgrade/` 或上一阶段独立审计报告。早期验收说明注明人工标注尚待提交。
- 在稳定提交上建立本地 `wxg-v1.0`。从该 Tag 创建 `ieg-v2.0`，在原仓库同级的 `../level-eval-ieg-v2` 建立 Git Worktree。桌面工作树工具未返回结果，改用 Git 原生命令，在本地验证了两条分支各自的 checkout。审计提交只包含本目录下的四份 Markdown。

## 现有技术与可复用边界

| 检查项 | 基准实现 | 核心入口 |
| --- | --- | --- |
| 前端 | 原生 HTML/CSS/JS，由 Python 生成。评测浏览器支持查看关卡、评审问题、引文和重写对照。盲标页面用浏览器本地存储并导出 CSV | `viewer/index.html`、`labels/labeling_sheet.html`、`scripts/build_html.py` |
| 后端与存储 | Python CLI 脚本及模块，持久化为 JSON、JSONL、CSV 和静态页面。基准没有 Web API、数据库、表结构或迁移 | `levelgen/`、`scripts/`、`data/`、`eval/`、`labels/`、`logs/usage.jsonl` |
| Agent 与 Planner | 按需求模板构造消息并请求生成，一次输出文字冒险关卡。脚本串起规则、Judge 和一次定向重写，历史任务没有 Agent 规划器、工具调用图或会话状态 | `levelgen/evalset.py`、`levelgen/generator.py`、`scripts/run_generate.py`、`scripts/run_all.sh` |
| 模型 Provider | 单一硅基流动 OpenAI-compatible 请求封装，带超时、重试、缓存、token/估价日志与累计预算检查。Provider 与路径在全局配置，缓存命中直接返回。历史 `seed_tag` 是缓存区分字段 | `levelgen/llm.py`、`levelgen/keyloader.py`、`configs/settings.yaml` |
| 规则层 | 已实现 H1–H10，五项结构阻断。可离线直接调用，历史输出的 `fail_list` 对齐 216/216 | `levelgen/checks.py` |
| 语义与校准 | 已有 v0–v3、三家族清单、四维合分、规则封顶、开发集偏移、重测、成对比较与统计工具。v3 对少量必需字段验收，引用主要用于展示 | `levelgen/judge*.py`、`levelgen/systems.py`、`levelgen/metrics.py`、`levelgen/stats.py`、`eval/` |
| Trace Explorer | 静态浏览器可回看内容与已有评测证据。生成原文、部分评审结构和重写对照分散在文件中，缺逐节点运行 ID、参数历史和完整 Provider 响应 | `viewer/index.html`、`data/levels/`、`eval/judge_v3_results.jsonl`、`logs/usage.jsonl` |
| Bad Case | 有分析报告、规则和清单中可回放的案例证据，适合作为首批案例输入。缺根因工单、处理状态和首次偏离节点记录 | `eval/badcases.md`、`scripts/build_html.py` |
| Golden Case | 固定题库、标注映射和留出切分已存在。生命周期、人工批准、发布及退役在 v2 设计范围内 | `data/eval_specs.json`、`labels/label_set_mapping.json`、`docs/DESIGN.md` |
| 版本回归 | 有重采样、Judge 重测、成对对照和离线报表重算。缺冻结的数据版本、显式候选/基线配对及回归门槛记录 | `scripts/report_retest.py`、`scripts/analyze_v3.py`、`eval/retest.json` |
| 重写 | 已有反馈提取、同模型定向重写一次、复评与部分盲化成对结果。原版和重写版可关联，渲染后的原/新 Prompt、完整请求和策略版本没有统一的存档 | `levelgen/rewrite.py`、`scripts/run_rewrite_loop.py`、`data/rewrites/`、`eval/rewrite_results.jsonl` |

H1–H10 依次检查 JSON 可解析、字段完整、三个选项、选项字段、选项差异、可推进、坏结局难度限制、结果分布、场景长度、儿童词表。H1/H2/H3/H4/H6 阻断。H10 只在儿童画像运行。规则返回布尔和详情，路径连通性受限于单关卡的 `result` 与 `next`；角色、物品和跨节点状态缺结构化契约。

## 基线验证

- 在原工作区以 `PYTHONDONTWRITEBYTECODE=1` 运行 `python -m unittest discover -s tests -v`，**5 项通过**。覆盖 JSON 失败阻断、Jaccard、216 份规则遍历、完美一致性 Kappa 和 bootstrap 区间输出。
- 以 Tag 导出两份临时副本。清空实验凭证环境后在其中一份依次运行 `compute_agreement.py`、`analyze_v3.py`、`report_rewrite.py`、`report_retest.py`、`report_triage.py` 和 `build_html.py`。六个脚本均执行完成；文件对比只发现重写成本和时延报告两处差异。常数基线触发 SciPy 的常量输入相关系数警告。详细差异见[数据血缘](01_data_lineage.md)。
- 本次解释器与已有依赖为 Python 3.12.14、NumPy 2.5.4、SciPy 1.18.1、PyYAML 6.0.3、requests 2.34.2。真实模型调用次数为 0。原版完整实验启动入口 `scripts/run_all.sh` 含付费调用，审计采用离线入口。
