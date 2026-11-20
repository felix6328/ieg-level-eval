# Phase 0 · 历史数据血缘

来源固定为 `wxg-v1.0`（`7ab99c7`）。以下结果属于历史实验或本次离线审计复算，统计时分别保留来源和时间。没有创建 IEG 实验，也没有在线重跑生成或 Judge。

| 数据 | 位置 | 已核实的链接与口径 |
| --- | --- | --- |
| 历史生成题库 | `configs/grid.yaml`、`levelgen/evalset.py`、`data/eval_specs.json` | 24 个唯一 `spec_id`。18 条常规为 6 主题 × 3 难度，轮换画像，另有 6 条难例。重新构建的对象与归档一致。每份关卡附带对应的 spec 快照 |
| 历史生成 | `data/levels/*.json`、`configs/settings.yaml` | 216 个唯一 `level_id`；每个 spec × A/B/C × 3 次各有唯一记录。A 为 Qwen2.5-7B + `gen_v1`，B 为同 7B + `gen_v2`，C 为 Qwen2.5-72B + `gen_v2`。每组 72 份，保存生成文本、解析结果及 token/延迟。216/216 原文非空，212/216 有解析对象，4 份解析失败保留在分母 |
| 历史初代 Judge | `eval/judge_results.jsonl`、`eval/judge_v2_results.jsonl`、`eval/judge_v2cal_results.jsonl` | 分别为 87、72、72 条，均能连到已存关卡。三个文件的 schema 与覆盖范围各自独立 |
| 历史 v3 Judge | `eval/judge_v3_results.jsonl`、`prompts/judge_v3_system.txt`、`levelgen/judge_v3.py` | 216 条结果，10 项规则的历史失败项与离线重跑完全匹配。19 道清单题（L1–L6、F1–F4、D1–D4、P1–P4、V1），另有 `spec_tension`。DeepSeek、GLM、Hunyuan 各 212 条有原始答案的记录，4 份解析失败由代码给各家族写入低分占位，各有 4 条。家族结果共 636 条含原始答案，应保留占位来源，独立计数 |
| 历史重测和成对比较 | `eval/judge_v3_retest.jsonl`、`eval/pairwise_eval.jsonl` | 40 份关卡重测、30 对成对实验，服务 Judge 稳定性和位置偏差分析。成对记录按 `a,b` 关联 |
| 标注参照 | `labels/label_set_mapping.json`、`labels/provisional_reference.csv`、`labels/human_labels.csv` | 40 个唯一 `label_id` 与 40 个不同的关卡相连；临时模型盲标 40 条，真人模板 40 行且 0 行完成。dev 15 / holdout 25 是关卡级划分。以 `spec_id` 分组，dev 有 9 种、holdout 有 15 种，其中 4 种重叠（`adv_inject`、`cyber_easy`、`cyber_normal`、`wuxia_easy`）。适用于历史窗口的复算，跨题独立性仍待新划分 |
| 历史分流 | `eval/triage.json`、`scripts/report_triage.py` | 54/216 自动通过（25.00%），57/216 自动拦截（26.39%），105/216 转人工队列（48.61%）。57 中 39 条确定性阻断、18 条硬规则通过但三家族一致否决。分流中的“人审”是应复核状态，本库人工决定为 0 |
| 历史重写 | `data/rewrites/`、`eval/rewrite_results.jsonl`、`eval/rewrite_loop.json` | 36 份原/重写对可连接到两个文件。B 组 10/28、C 组 5/8 重写后满足历史质量门槛，A 未参与。33 对含成对复核字段。对照重采样用同一 spec 的其他两份已生成样本估计 |
| 历史调用和费用 | `logs/usage.jsonl`、`docs/COST.md`、`configs/settings.yaml` | 日志共有 1,854 行，其中 `gen:A/B/C` 各 72 行。记录时间在 2026-11-15 18:27:12–20:34:59，未标时区。账面估价字段合计 ¥7.404414，包含所有已记录用途。7B 用免费档口径，72B 用假设单价。日志没有请求 ID 和逐关关联，控制台账单未核验 |
| 其他题库 | 基准树、项目文档和本机对应材料 | 未发现一套可核验的 LevelEval 100 条完整数据集。面试说明中的“至少 100 关、2 名标注者”是后续标注计划。40 条标注映射是 216 份样本的子集，历史 24 条题库是生成任务。若另有 100 条文件，需按原来源和原划分另建版本 |

4 条解析失败为 `A__adv_overconstrained`、`A__wuxia_easy`、`B__wuxia_easy__s2`、`B__wuxia_hard`。212/216 表示归档输出解析率，仅凭成功调用日志和产物无法回填所有请求尝试、超时或失败，因此新实验指标需要独立的请求台账。

## 已复算的历史指标

- 规则通过率为无 H1/H2/H3/H4/H6 阻断的输出数 ÷ 已进入历史规则评测的输出数。A 为 43/72，B 为 62/72，C 为 72/72，合计 177/216。四个 JSON 失败已计入。
- 历史合格率以硬规则通过且 v3 三家族校准集成的四维最低分 ≥3 为条件。A 为 14/72，B 为 44/72，C 为 64/72。该指标依赖临时参照的校准偏移，人工验收率为不可计算。
- 历史分流采用规则优先，以及三个校准家族各自最低维 ≥3 的一致投票。转人工比例 105/216 代表建议人审量。单个家族四维分、集成四维分和策略投票不可用同一个“通过率”混算。
- 历史重写后合格数 ÷ 对应重写样本数，B 为 10/28，C 为 5/8。重写成本分母为历史策略合格的关卡数量，旧耗时公式是串行摊销估算；这两项没有真人验收或人工耗时的证据。

## 归档与复算差异

与 Tag 里的归档逐文件比较，共识、主要结果、重测、分流及静态页面均与离线重算副本一致。`eval/rewrite_loop.json` 和 `eval/rewrite_loop.md` 的少量成本/耗时字段不同，例如每关三家 Judge 估价 ¥0.0110 → ¥0.0111、C 组闭环估价 ¥0.0184 → ¥0.0185。重写成功计数、合格率、成对结果一致。当前脚本对带 `judge_v3` 标签的日志直接聚合，既有日志缺逐任务/批次 ID，无法从现存文件确定归档和复算差异的精确来源。保留原始报告，后续把归档值和复算值标为不同产物。

以下 SHA-256 用于迁移核对。每个目录取所有已跟踪文件，按相对路径排序，对每行 `<文件 SHA-256><两个空格><相对路径><LF>` 再做 SHA-256。

| 目录 | 文件数 | SHA-256 |
| --- | ---: | --- |
| `data/` | 253 | `757bde79b8bc65f99018e137ed16a5b45fc956b494fbd4eced1d72c4d23a6282` |
| `eval/` | 22 | `8e93a4a4e16b0ac6c797655fd9eeb18d357550f457bf9c96b55b0a8defea7b2a` |
| `labels/` | 5 | `2a3e4f534e06f3e13e9908cdd29552909b50466717b5d37c28fcb5f81b90f9ac` |
| `logs/` | 1 | `12e4afcaca40a76f05fab831d25331b0a571101becf204c47781f91a713341ac` |
